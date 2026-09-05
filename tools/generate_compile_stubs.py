#!/usr/bin/env python3
"""Generate minimal Java ABI stubs from allowlisted local smali declarations."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

ACCESS = {"public", "private", "protected", "static", "final", "synchronized",
          "declared-synchronized", "bridge", "varargs", "native", "abstract",
          "strictfp", "synthetic", "interface", "annotation", "enum"}
DESC_RE = re.compile(r"^L(?:[A-Za-z_$][\w$]*/)*[A-Za-z_$][\w$]*;$")
METHOD_RE = re.compile(r"^\.method\s+(.+?)\s+([^\s(]+)(\(.*)$")
TYPE_RE = re.compile(r"(?:\[*[ZBSCIJFDV]|\[*L[^;]+;)")
HEADER = "// GENERATED COMPILE-ONLY ABI STUB. DO NOT COMMIT OR PACKAGE.\n"


class ContractError(ValueError):
    pass


def _class_path(descriptor: str) -> Path:
    if not isinstance(descriptor, str) or not DESC_RE.fullmatch(descriptor):
        raise ContractError(f"unsafe class descriptor: {descriptor!r}")
    return Path(*descriptor[1:-1].split("/")).with_suffix(".smali")


def _access(value, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or any(x not in ACCESS for x in value):
        raise ContractError(f"invalid access flags at {where}")
    if len(set(value)) != len(value):
        raise ContractError(f"duplicate access flag at {where}")
    return tuple(value)


def _method(value, where: str, hook: bool) -> dict:
    required = {"name", "descriptor", "access", "throws"}
    allowed = required | ({"provenance", "verify_in_smali"} if hook else set())
    if not isinstance(value, dict) or set(value) - allowed or not required <= set(value):
        raise ContractError(f"invalid method keys at {where}")
    name = value["name"]
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_$][\w$]*", name):
        raise ContractError(f"unsafe method name at {where}")
    parse_method_descriptor(value["descriptor"])
    throws = value["throws"]
    if not isinstance(throws, list):
        raise ContractError(f"throws must be a list at {where}")
    for item in throws:
        _class_path(item)
    if hook and (not value.get("provenance") or value.get("verify_in_smali") is not True):
        raise ContractError(f"project hook must be attributed and verified at {where}")
    return {**value, "access": _access(value["access"], where)}


def load_contract(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ContractError("unsupported contract schema")
    roots = raw.get("roots")
    if not isinstance(roots, list) or not roots or len(set(roots)) != len(roots):
        raise ContractError("roots must be a unique non-empty list")
    if any(not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", x or "") for x in roots):
        raise ContractError("unsafe root name")
    classes = raw.get("classes")
    if not isinstance(classes, list) or not classes:
        raise ContractError("classes must be non-empty")
    seen_classes = set()
    normalized = []
    for index, cls in enumerate(classes):
        where = f"classes[{index}]"
        required = {"descriptor", "root", "access", "super", "java_super", "java_kind",
                    "stock_methods", "project_hooks"}
        if not isinstance(cls, dict) or set(cls) != required:
            raise ContractError(f"invalid class keys at {where}")
        descriptor = cls["descriptor"]
        _class_path(descriptor)
        _class_path(cls["super"])
        java_super = cls["java_super"]
        if java_super is not None:
            _class_path(java_super)
        if descriptor in seen_classes:
            raise ContractError(f"duplicate class {descriptor}")
        seen_classes.add(descriptor)
        if cls["root"] not in roots or cls["java_kind"] not in {"class", "abstract_class", "interface"}:
            raise ContractError(f"invalid root or java_kind at {where}")
        if cls["java_kind"] == "interface" and java_super is not None:
            raise ContractError(f"interface java_super must be null at {where}")
        methods = []
        identities = set()
        for group, hook in (("stock_methods", False), ("project_hooks", True)):
            if not isinstance(cls[group], list):
                raise ContractError(f"{group} must be a list at {where}")
            for j, item in enumerate(cls[group]):
                method = _method(item, f"{where}.{group}[{j}]", hook)
                identity = (method["name"], method["descriptor"])
                if identity in identities:
                    raise ContractError(f"duplicate method {identity} at {where}")
                identities.add(identity)
                methods.append((group, method))
        normalized.append({**cls, "access": _access(cls["access"], where), "methods": methods})
    return {"roots": tuple(roots), "classes": normalized}


def parse_method_descriptor(descriptor: str) -> tuple[list[str], str]:
    if not isinstance(descriptor, str) or not descriptor.startswith("(") or ")" not in descriptor:
        raise ContractError(f"invalid method descriptor: {descriptor!r}")
    split = descriptor.index(")")
    args_text, return_text = descriptor[1:split], descriptor[split + 1:]
    args = TYPE_RE.findall(args_text)
    if "".join(args) != args_text or any(x == "V" for x in args):
        raise ContractError(f"invalid method descriptor: {descriptor!r}")
    returns = TYPE_RE.findall(return_text)
    if len(returns) != 1 or returns[0] != return_text:
        raise ContractError(f"invalid method descriptor: {descriptor!r}")
    for item in args + returns:
        base = item.lstrip("[")
        if base.startswith("L"):
            _class_path(base)
    return args, return_text


def parse_smali(path: Path) -> dict:
    # Reading is necessary for parsing, but only declarations and Throws are retained.
    lines = path.read_text(encoding="utf-8").splitlines()
    class_rows = [x.strip().split() for x in lines if x.startswith(".class ")]
    super_rows = [x.strip().split() for x in lines if x.startswith(".super ")]
    if len(class_rows) != 1 or len(super_rows) != 1:
        raise ContractError(f"expected exactly one .class and .super in {path.name}")
    class_desc = class_rows[0][-1]
    methods = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        match = METHOD_RE.fullmatch(line)
        if not match:
            i += 1
            continue
        flags = tuple(match.group(1).split())
        name, descriptor = match.group(2), match.group(3)
        throws = []
        i += 1
        while i < len(lines) and lines[i].strip() != ".end method":
            if lines[i].strip() == ".annotation system Ldalvik/annotation/Throws;":
                i += 1
                while i < len(lines) and lines[i].strip() != ".end annotation":
                    token = lines[i].strip().rstrip(",")
                    if DESC_RE.fullmatch(token):
                        throws.append(token)
                    i += 1
            i += 1
        if i >= len(lines):
            raise ContractError(f"unterminated method {name}{descriptor} in {path.name}")
        methods.append({"name": name, "descriptor": descriptor, "access": flags,
                        "throws": tuple(throws)})
        i += 1
    return {"descriptor": class_desc, "access": tuple(class_rows[0][1:-1]),
            "super": super_rows[0][-1], "methods": methods}


def _java_type(descriptor: str) -> str:
    dimensions = len(descriptor) - len(descriptor.lstrip("["))
    base = descriptor[dimensions:]
    primitive = {"Z": "boolean", "B": "byte", "S": "short", "C": "char",
                 "I": "int", "J": "long", "F": "float", "D": "double", "V": "void"}
    name = primitive.get(base, base[1:-1].replace("/", ".").replace("$", "."))
    return name + "[]" * dimensions


def _java_flags(flags: tuple[str, ...], interface_method: bool = False) -> str:
    mapping = {"declared-synchronized": "synchronized"}
    skipped = {"bridge", "synthetic", "varargs", "native", "interface", "annotation", "enum"}
    result = [mapping.get(x, x) for x in flags if x not in skipped]
    if interface_method:
        result = [x for x in result if x not in {"public", "abstract"}]
    return (" ".join(result) + " ") if result else ""


def render_java(cls: dict, observed: dict) -> str:
    binary = cls["descriptor"][1:-1].replace("/", ".")
    package, simple = binary.rsplit(".", 1)
    kind = cls["java_kind"]
    if kind == "interface":
        declaration = f"public interface {simple}"
    else:
        prefix = "public abstract class" if kind == "abstract_class" else "public class"
        declaration = f"{prefix} {simple}"
        if cls["java_super"] is not None:
            declaration += f" extends {_java_type(cls['java_super'])}"
    rows = [HEADER.rstrip(), f"package {package};", "", declaration + " {"]
    observed_by_id = {(m["name"], m["descriptor"]): m for m in observed["methods"]}
    for group, method in cls["methods"]:
        args, returns = parse_method_descriptor(method["descriptor"])
        args_java = ", ".join(f"{_java_type(x)} arg{i}" for i, x in enumerate(args))
        throws = observed_by_id[(method["name"], method["descriptor"])]["throws"]
        throws_java = " throws " + ", ".join(_java_type(x) for x in throws) if throws else ""
        marker = "stock-extracted" if group == "stock_methods" else "project-added-hook"
        rows.append(f"    // ABI source: {marker}")
        signature = (f"    {_java_flags(method['access'], kind == 'interface')}"
                     f"{_java_type(returns)} {method['name']}({args_java}){throws_java}")
        if kind == "interface" or "abstract" in method["access"]:
            rows.append(signature + ";")
            continue
        body = {"void": "", "boolean": "return false;", "byte": "return 0;",
                "short": "return 0;", "char": "return '\\0';", "int": "return 0;",
                "long": "return 0L;", "float": "return 0.0f;", "double": "return 0.0d;"}
        statement = body.get(_java_type(returns), "return null;")
        rows.append(signature + " {" + ((" " + statement + " ") if statement else "") + "}")
    rows.extend(["}", ""])
    return "\n".join(rows)


def verify_class(cls: dict, parsed: dict) -> None:
    if parsed["descriptor"] != cls["descriptor"] or parsed["super"] != cls["super"]:
        raise ContractError(f"class/super drift for {cls['descriptor']}")
    if parsed["access"] != cls["access"]:
        raise ContractError(f"class access drift for {cls['descriptor']}")
    for group, expected in cls["methods"]:
        matches = [m for m in parsed["methods"]
                   if m["name"] == expected["name"] and m["descriptor"] == expected["descriptor"]]
        if len(matches) != 1:
            raise ContractError(f"expected exactly one {expected['name']}{expected['descriptor']} in {cls['descriptor']}; found {len(matches)}")
        actual = matches[0]
        if actual["access"] != expected["access"]:
            raise ContractError(f"method access drift for {cls['descriptor']}->{expected['name']}{expected['descriptor']}")
        if actual["throws"] != tuple(expected["throws"]):
            raise ContractError(f"throws drift for {cls['descriptor']}->{expected['name']}{expected['descriptor']}")


def _safe_source(root: Path, relative: Path) -> Path:
    resolved_root = root.resolve(strict=True)
    if not resolved_root.is_dir():
        raise ContractError(f"smali root is not a directory: {root}")
    candidate = resolved_root.joinpath(relative)
    resolved = candidate.resolve(strict=True)
    if not resolved.is_file() or resolved_root not in resolved.parents:
        raise ContractError(f"unsafe or missing smali path: {relative.as_posix()}")
    return resolved


def _write_file_atomic(path: Path, content: bytes, allow_identical: bool) -> None:
    if path.exists():
        if allow_identical and path.is_file() and path.read_bytes() == content:
            return
        raise ContractError(f"refusing to overwrite existing path: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def generate(contract_path: Path, roots: dict[str, Path], output: Path, report: Path,
             allow_identical: bool = False) -> dict:
    contract = load_contract(contract_path)
    if set(roots) != set(contract["roots"]):
        raise ContractError(f"smali root names must be exactly {sorted(contract['roots'])}")
    output = output.resolve()
    report = report.resolve()
    if output == report or output in report.parents or report in output.parents:
        raise ContractError("output and report paths must be separate")
    if report.exists() and not output.exists():
        raise ContractError("refusing existing report without a matching existing output")
    rendered = {}
    provenance = {"stock-extracted": 0, "project-added-hook": 0}
    for cls in contract["classes"]:
        relative = _class_path(cls["descriptor"])
        source = _safe_source(roots[cls["root"]], relative)
        parsed = parse_smali(source)
        verify_class(cls, parsed)
        java_relative = relative.with_suffix(".java")
        rendered[java_relative] = render_java(cls, parsed).encode("utf-8")
        for group, _ in cls["methods"]:
            provenance["project-added-hook" if group == "project_hooks" else "stock-extracted"] += 1
    created_output = False
    if output.exists():
        if not allow_identical or not output.is_dir():
            raise ContractError(f"refusing to overwrite existing output: {output}")
        existing = {p.relative_to(output): p.read_bytes() for p in output.rglob("*.java")}
        all_files = [p for p in output.rglob("*") if p.is_file()]
        if existing != rendered or len(all_files) != len(existing):
            raise ContractError("existing output conflicts with generated stubs")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".compile-stubs-", dir=output.parent))
        try:
            for relative, content in rendered.items():
                target = stage / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            os.replace(stage, output)
            created_output = True
        except BaseException:
            shutil.rmtree(stage, ignore_errors=True)
            raise
    result = {
        "schema_version": 1,
        "status": "verified-and-generated",
        "class_count": len(rendered),
        "method_provenance_counts": provenance,
        "files": [{"path": p.as_posix(), "sha256": hashlib.sha256(rendered[p]).hexdigest()}
                  for p in sorted(rendered, key=lambda x: x.as_posix())],
        "safety": {"instructions_copied": False, "fields_copied": False,
                   "parameter_names_copied": False, "candidate_dex_eligible": False}
    }
    payload = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        _write_file_atomic(report, payload, allow_identical)
    except BaseException:
        if created_output:
            shutil.rmtree(output, ignore_errors=True)
        raise
    return result


def _root_arg(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("expected NAME=PATH")
    name, path = value.split("=", 1)
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", name) or not path:
        raise argparse.ArgumentTypeError("unsafe or empty NAME=PATH")
    return name, Path(path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--smali-root", type=_root_arg, action="append", required=True,
                        help="named private decoded root as NAME=PATH; repeat for every contract root")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--allow-identical", action="store_true",
                        help="accept, but never replace, byte-identical existing output/report")
    args = parser.parse_args(argv)
    roots = dict(args.smali_root)
    if len(roots) != len(args.smali_root):
        parser.error("duplicate --smali-root name")
    try:
        result = generate(args.contract, roots, args.output, args.report, args.allow_identical)
    except (ContractError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"generated {result['class_count']} compile-only ABI stubs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
