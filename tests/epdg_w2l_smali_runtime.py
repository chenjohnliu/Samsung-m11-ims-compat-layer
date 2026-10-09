"""Small executable subset of smali used by the EC2 W2L helper tests.

This is deliberately an instruction interpreter, not a second implementation of
the trial state machine.  Tests load the shipped helper asset and execute its
actual branches while this module supplies Android/ePDG boundary mocks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class Method:
    signature: str
    instructions: list[str]
    labels: dict[str, int]
    catches: list[tuple[str, str, str, str]]


@dataclass
class Obj:
    kind: str
    fields: dict[str, Any] = field(default_factory=dict)


class SmaliThrown(RuntimeError):
    def __init__(self, kind: str, value: Any = None):
        super().__init__(kind)
        self.kind = kind
        self.value = value


class SmaliClass:
    METHOD = re.compile(r"^\.method\s+(.+)$")
    FIELD = re.compile(r"^\.field\s+.*?([A-Za-z0-9_$]+):(\S+?)(?:\s+=\s+(.+))?$")

    def __init__(self, path: Path):
        self.path = path
        self.methods: dict[str, Method] = {}
        self.static: dict[str, Any] = {}
        self._parse(path.read_text(encoding="utf-8"))

    def _parse(self, text: str) -> None:
        lines = text.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            field_match = self.FIELD.match(line)
            if field_match:
                name, descriptor, raw = field_match.groups()
                if raw is None:
                    value = 0 if descriptor in {"Z", "B", "S", "C", "I", "J", "F", "D"} else None
                elif raw.startswith('"'):
                    value = raw[1:-1]
                elif raw == "true":
                    value = 1
                elif raw == "false":
                    value = 0
                else:
                    value = int(raw, 0)
                self.static[name] = value
            match = self.METHOD.match(line)
            if not match:
                i += 1
                continue
            signature = match.group(1)
            body: list[str] = []
            labels: dict[str, int] = {}
            catches: list[tuple[str, str, str, str]] = []
            i += 1
            while i < len(lines) and lines[i].strip() != ".end method":
                item = lines[i].strip()
                if item.startswith(":"):
                    labels[item[1:]] = len(body)
                elif item.startswith(".catch"):
                    cm = re.match(r"\.catch(?:all|\s+(\S+))\s+\{:(\S+)\s+\.\.\s+:(\S+)\}\s+:(\S+)", item)
                    if cm:
                        catches.append((cm.group(1) or "Ljava/lang/Throwable;", cm.group(2), cm.group(3), cm.group(4)))
                elif item and not item.startswith((".", "#")):
                    body.append(item)
                i += 1
            # Labels were counted against executable instructions; recalculate
            # because directives/comments were intentionally omitted.
            executable = []
            labels = {}
            for raw_line in lines[self._method_start(lines, signature) + 1 : i]:
                item = raw_line.strip()
                if item.startswith(":"):
                    labels[item[1:]] = len(executable)
                elif item and not item.startswith((".", "#")):
                    executable.append(item)
            self.methods[signature] = Method(signature, executable, labels, catches)
            i += 1

    @staticmethod
    def _method_start(lines: list[str], signature: str) -> int:
        needle = ".method " + signature
        return next(i for i, line in enumerate(lines) if line.strip() == needle)


class Runtime:
    INVOKE = re.compile(r"invoke-(?:static|virtual|direct|interface)(?:/range)?\s+\{([^}]*)\},\s+(L[^;]+;)->([^\s]+)")
    MEMBER = re.compile(r"[sip]get(?:-object|-boolean)?\s+([^,]+),\s*(?:([^,]+),\s*)?(L[^;]+;)->([^:]+):(\S+)")

    def __init__(self, smali: SmaliClass):
        self.smali = smali
        self.external: dict[str, Callable[..., Any]] = {}
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.monitors: dict[int, int] = {}
        self.last_result: Any = None
        self.pending_exception: Any = None
        self.enums = {
            "Lcom/sec/epdg/data/Constants/ImsConstants$EpdgCallStatus;->CALL_VOICEONLY": "CALL_VOICEONLY",
            "Lcom/sec/epdg/data/Constants/ImsConstants$EpdgCallStatus;->CALL_IDLE": "CALL_IDLE",
            "Lcom/sec/epdg/data/Constants/EpdgConstants$TriState;->TRI_TRUE": "TRI_TRUE",
            "Lcom/sec/epdg/data/Constants/MapconConstants$MapconApnType;->APN_TYPE_IMS": "APN_TYPE_IMS",
            "Lcom/sec/epdg/data/Constants/MapconConstants$MapconMode;->LTE": "LTE",
        }

    def boot(self) -> None:
        signature = next((s for s in self.smali.methods if s.endswith("constructor <clinit>()V")), None)
        if signature:
            self.run(signature)

    def bind(self, owner_method: str, func: Callable[..., Any]) -> None:
        self.external[owner_method] = func

    def run(self, signature: str, *args: Any) -> Any:
        method = self.smali.methods[signature]
        regs: dict[str, Any] = {f"p{i}": value for i, value in enumerate(args)}
        pc = 0
        while pc < len(method.instructions):
            insn = method.instructions[pc]
            try:
                jumped, value = self._step(insn, regs, method)
            except SmaliThrown as exc:
                handler = self._handler(method, pc, exc.kind)
                if handler is None:
                    raise
                self.pending_exception = exc.value if exc.value is not None else exc
                pc = method.labels[handler]
                continue
            if jumped == "return":
                return value
            if jumped is not None:
                pc = method.labels[jumped]
            else:
                pc += 1
        return None

    def _handler(self, method: Method, pc: int, kind: str) -> str | None:
        for caught, start, end, handler in method.catches:
            if method.labels.get(start, -1) <= pc < method.labels.get(end, -1):
                if caught in ("Ljava/lang/Throwable;", kind, "Ljava/lang/RuntimeException;"):
                    return handler
        return None

    @staticmethod
    def _reg_list(raw: str) -> list[str]:
        raw = raw.strip()
        if not raw:
            return []
        if ".." in raw:
            first, last = [x.strip() for x in raw.split("..")]
            prefix = first[0]
            return [f"{prefix}{i}" for i in range(int(first[1:]), int(last[1:]) + 1)]
        return [x.strip() for x in raw.split(",")]

    @staticmethod
    def _literal(raw: str) -> int:
        return int(raw.rstrip("LlSsTt"), 0)

    @staticmethod
    def _dex_equal(left: Any, right: Any) -> bool:
        # DEX if-eq/if-ne compare object registers by reference, while Python
        # dataclasses/lists otherwise compare structurally.
        if isinstance(left, (Obj, list, dict)) or isinstance(right, (Obj, list, dict)):
            return left is right
        return left == right

    def _step(self, insn: str, r: dict[str, Any], method: Method) -> tuple[str | None, Any]:
        op, _, tail = insn.partition(" ")
        if op.startswith("const-string"):
            dst, raw = [x.strip() for x in tail.split(",", 1)]
            r[dst] = bytes(raw[1:-1], "utf-8").decode("unicode_escape")
        elif op.startswith("const"):
            dst, raw = [x.strip() for x in tail.split(",", 1)]
            r[dst] = self._literal(raw)
        elif op.startswith("move-result"):
            r[tail.strip()] = self.last_result
        elif op == "move-exception":
            r[tail.strip()] = self.pending_exception
        elif op.startswith("move"):
            dst, src = [x.strip() for x in tail.split(",", 1)]
            r[dst] = r.get(src)
        elif op == "new-array":
            dst, size_reg, _ = [x.strip() for x in tail.split(",", 2)]
            r[dst] = [None] * int(r[size_reg])
        elif op == "new-instance":
            dst, kind = [x.strip() for x in tail.split(",", 1)]
            r[dst] = Obj(kind)
        elif op.startswith("sget"):
            dst, member = [x.strip() for x in tail.split(",", 1)]
            name = member.split("->", 1)[1].split(":", 1)[0]
            r[dst] = self.enums.get(member.split(":", 1)[0], self.smali.static.get(name))
        elif op.startswith("sput"):
            src, member = [x.strip() for x in tail.split(",", 1)]
            name = member.split("->", 1)[1].split(":", 1)[0]
            self.smali.static[name] = r.get(src)
        elif op.startswith("aget"):
            dst, array, index = [x.strip() for x in tail.split(",")]
            r[dst] = r[array][int(r[index])]
        elif op.startswith("aput"):
            src, array, index = [x.strip() for x in tail.split(",")]
            r[array][int(r[index])] = r.get(src)
        elif op.startswith("add-int/lit"):
            dst, src, literal = [x.strip() for x in tail.split(",")]
            r[dst] = int(r[src]) + self._literal(literal)
        elif op == "add-int":
            dst, left, right = [x.strip() for x in tail.split(",")]
            r[dst] = int(r[left]) + int(r[right])
        elif op.startswith("iget"):
            dst, obj_reg, member = [x.strip() for x in tail.split(",", 2)]
            name = member.split("->", 1)[1].split(":", 1)[0]
            r[dst] = r[obj_reg].fields.get(name)
        elif op.startswith("iput"):
            src, obj_reg, member = [x.strip() for x in tail.split(",", 2)]
            name = member.split("->", 1)[1].split(":", 1)[0]
            r[obj_reg].fields[name] = r.get(src)
        elif op.startswith("invoke-"):
            match = self.INVOKE.fullmatch(insn)
            if not match:
                raise AssertionError(f"unsupported invoke: {insn}")
            regs, owner, called = match.groups()
            values = tuple(r.get(reg) for reg in self._reg_list(regs))
            key = owner + "->" + called
            self.calls.append((key, values))
            internal = next((s for s in self.smali.methods if s.split()[-1] == called), None) if owner == "Lcom/sec/epdg/M11qW2LTrial;" else None
            if internal:
                self.last_result = self.run(internal, *values)
            elif key in self.external:
                self.last_result = self.external[key](*values)
            else:
                self.last_result = self._builtin(key, values)
        elif op.startswith("if-"):
            operands, label = tail.rsplit(",", 1)
            values = [r.get(x.strip()) for x in operands.split(",")]
            if op == "if-eqz":
                take = values[0] in (None, 0, False)
            elif op == "if-nez":
                take = values[0] not in (None, 0, False)
            elif op == "if-ltz":
                take = int(values[0]) < 0
            elif op == "if-gez":
                take = int(values[0]) >= 0
            elif op == "if-gtz":
                take = int(values[0]) > 0
            elif op == "if-lez":
                take = int(values[0]) <= 0
            else:
                a, b = values
                if op == "if-eq":
                    take = self._dex_equal(a, b)
                elif op == "if-ne":
                    take = not self._dex_equal(a, b)
                elif op == "if-lt":
                    take = a < b
                elif op == "if-ge":
                    take = a >= b
                elif op == "if-gt":
                    take = a > b
                elif op == "if-le":
                    take = a <= b
                else:
                    raise AssertionError(f"unsupported branch: {op}")
            if take:
                return label.strip()[1:], None
        elif op.startswith("goto"):
            return tail.strip()[1:], None
        elif op == "monitor-enter":
            key = id(r[tail.strip()])
            self.monitors[key] = self.monitors.get(key, 0) + 1
        elif op == "monitor-exit":
            key = id(r[tail.strip()])
            if self.monitors.get(key, 0) <= 0:
                raise AssertionError("unbalanced monitor-exit")
            self.monitors[key] -= 1
        elif op == "check-cast" or op == "nop":
            pass
        elif op == "throw":
            value = r.get(tail.strip())
            if isinstance(value, SmaliThrown):
                raise value
            raise SmaliThrown("Ljava/lang/Throwable;", value)
        elif op.startswith("return"):
            return "return", None if op == "return-void" else r.get(tail.strip())
        else:
            raise AssertionError(f"unsupported instruction in {method.signature}: {insn}")
        return None, None

    def _builtin(self, key: str, values: tuple[Any, ...]) -> Any:
        if key == "Ljava/lang/Object;-><init>()V":
            return None
        if key == "Ljava/lang/StringBuilder;-><init>()V":
            values[0].fields["text"] = ""
            return None
        if key.startswith("Ljava/lang/StringBuilder;->append("):
            values[0].fields["text"] = values[0].fields.get("text", "") + str(values[1])
            return values[0]
        if key == "Ljava/lang/StringBuilder;->toString()Ljava/lang/String;":
            return values[0].fields.get("text", "")
        if key in ("Ljava/lang/String;->equals(Ljava/lang/Object;)Z", "Ljava/lang/String;->equalsIgnoreCase(Ljava/lang/String;)Z"):
            if key.endswith("equalsIgnoreCase(Ljava/lang/String;)Z"):
                return int(str(values[0]).lower() == str(values[1]).lower())
            return int(values[0] == values[1])
        raise AssertionError(f"unbound external method: {key}")


def method(smali: SmaliClass, suffix: str) -> str:
    matches = [signature for signature in smali.methods if signature.split()[-1] == suffix]
    if len(matches) != 1:
        raise AssertionError(f"expected one method {suffix}, found {matches}")
    return matches[0]
