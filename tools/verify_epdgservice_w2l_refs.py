#!/usr/bin/env python3
"""Check EC2 helper Samsung member references against the final decoded APK."""

import argparse
import json
import re
from pathlib import Path

CLASS = re.compile(r"(?m)^\.class[ \t]+(?:(.*?) +)?(L[^;]+;)$")
METHOD = re.compile(r"(?m)^\.method\s+([^\n]+?)\s+([^\s]+\([^\n]+)$")
FIELD = re.compile(r"(?m)^\.field[ \t]+(?:(.*?) +)?([^\s:]+:[^\s=]+)")
REFERENCE = re.compile(r"(Lcom/sec/[^;]+;)->([^\s,]+)")


def inventory(root):
    result = {}
    for path in root.rglob("*.smali"):
        text = path.read_text(encoding="utf-8")
        found = CLASS.search(text)
        if found is None:
            raise ValueError(f"missing class declaration: {path.name}")
        owner = found.group(2)
        superclass = re.search(r"(?m)^\.super\s+(L[^;]+;)$", text)
        if owner in result:
            raise ValueError(f"duplicate class: {owner}")
        result[owner] = {"flags": (found.group(1) or "").split(), "super": superclass.group(1) if superclass else None,
                         "members": {signature: flags.split() for flags, signature in METHOD.findall(text) + FIELD.findall(text)}}
    return result


def resolve(classes, owner, member):
    seen = set()
    while owner in classes and owner not in seen:
        seen.add(owner)
        info = classes[owner]
        if member in info["members"]:
            return owner, info["members"][member]
        owner = info["super"]
    raise ValueError(f"unresolved Samsung member: {owner}->{member}")


def verify(root):
    classes = inventory(root)
    owner = "Lcom/sec/epdg/M11qW2LTrial;"
    helper = root / "com/sec/epdg/M11qW2LTrial.smali"
    text = helper.read_text(encoding="utf-8")
    references = set(REFERENCE.findall(text))
    for target, member in sorted(references):
        declaring, flags = resolve(classes, target, member)
        if declaring != owner and "private" in flags:
            raise ValueError(f"inaccessible private member: {declaring}->{member}")
        same_package = owner.rsplit("/", 1)[0] == declaring.rsplit("/", 1)[0]
        if declaring != owner and "public" not in flags and not same_package:
            raise ValueError(f"inaccessible package/protected member: {declaring}->{member}")
    return {"status": "PASS", "resolved_samsung_helper_references": len(references),
            "android_framework_reference_validation": "not performed by this tool",
            "runtime_validated": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smali-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify(args.smali_root)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
