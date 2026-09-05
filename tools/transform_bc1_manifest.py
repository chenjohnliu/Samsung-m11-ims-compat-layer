#!/usr/bin/env python3
"""Apply the project-authored BC1 MMTEL discovery manifest transformation."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


class TransformError(ValueError):
    pass


def load_contract(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TransformError(f"cannot read contract: {exc}") from exc
    expected_top = {"schema_version", "transformation_id", "input", "service",
                    "excluded_features"}
    if not isinstance(raw, dict) or set(raw) != expected_top or raw["schema_version"] != 1:
        raise TransformError("unsupported or malformed contract")
    if raw["transformation_id"] != "BC1-modern-mmtel-discovery":
        raise TransformError("unexpected transformation_id")
    inp = raw["input"]
    service = raw["service"]
    if not isinstance(inp, dict) or set(inp) != {"manifest_package", "android_namespace"}:
        raise TransformError("malformed input contract")
    if inp["manifest_package"] != "com.sec.imsservice":
        raise TransformError("unexpected manifest package contract")
    if inp["android_namespace"] != "http://schemas.android.com/apk/res/android":
        raise TransformError("unexpected Android namespace contract")
    service_keys = {"name", "permission", "enabled", "exported", "single_user",
                    "action", "metadata"}
    if not isinstance(service, dict) or set(service) != service_keys:
        raise TransformError("malformed service contract")
    expected_strings = {
        "name": "com.sec.internal.google.GoogleModernImsService",
        "permission": "android.permission.BIND_IMS_SERVICE",
        "action": "android.telephony.ims.ImsService",
    }
    if any(service[key] != value for key, value in expected_strings.items()):
        raise TransformError("unexpected service identity contract")
    if any(service[key] is not True for key in ("enabled", "exported", "single_user")):
        raise TransformError("BC1 service booleans must be true")
    if service["metadata"] != {"android.telephony.ims.MMTEL_FEATURE": True}:
        raise TransformError("BC1 must declare MMTEL_FEATURE=true only")
    excluded = raw["excluded_features"]
    expected_excluded = {"android.telephony.ims.EMERGENCY_MMTEL_FEATURE",
                         "android.telephony.ims.RCS_FEATURE"}
    if not isinstance(excluded, list) or set(excluded) != expected_excluded or len(excluded) != 2:
        raise TransformError("malformed excluded_features contract")
    return raw


def _parse_xml(data: bytes) -> ET.ElementTree:
    try:
        parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
        return ET.ElementTree(ET.fromstring(data, parser=parser))
    except ET.ParseError as exc:
        raise TransformError(f"malformed AndroidManifest.xml: {exc}") from exc


def _tag(local: str) -> str:
    return local


def _attr(namespace: str, local: str) -> str:
    return f"{{{namespace}}}{local}"


def _assert_source_shape(tree: ET.ElementTree, contract: dict) -> ET.Element:
    root = tree.getroot()
    if root.tag != _tag("manifest"):
        raise TransformError("root must be manifest")
    if root.get("package") != contract["input"]["manifest_package"]:
        raise TransformError("manifest package drift")
    namespace = contract["input"]["android_namespace"]
    # A real decoded manifest must use the Android namespace on at least one attribute.
    if not any(any(key.startswith(f"{{{namespace}}}") for key in element.attrib)
               for element in tree.iter()):
        raise TransformError("required Android namespace is absent")
    applications = [child for child in root if child.tag == _tag("application")]
    if len(applications) != 1:
        raise TransformError(f"expected exactly one application; found {len(applications)}")
    name_attr = _attr(namespace, "name")
    target = contract["service"]["name"]
    services = [element for element in tree.iter("service") if element.get(name_attr) == target]
    if services:
        raise TransformError(f"target service already exists; found {len(services)}")
    action = contract["service"]["action"]
    action_hits = [element for element in tree.iter("action") if element.get(name_attr) == action]
    if action_hits:
        raise TransformError(f"target action already exists; found {len(action_hits)}")
    protected_names = set(contract["service"]["metadata"]) | set(contract["excluded_features"])
    metadata_hits = [element for element in tree.iter("meta-data")
                     if element.get(name_attr) in protected_names]
    if metadata_hits:
        raise TransformError(f"target or excluded IMS metadata already exists; found {len(metadata_hits)}")
    return applications[0]


def _insert(tree: ET.ElementTree, application: ET.Element, contract: dict) -> None:
    namespace = contract["input"]["android_namespace"]
    service_spec = contract["service"]
    android = lambda name: _attr(namespace, name)
    service = ET.Element("service", {
        android("name"): service_spec["name"],
        android("permission"): service_spec["permission"],
        android("enabled"): "true",
        android("exported"): "true",
        android("singleUser"): "true",
    })
    ET.SubElement(service, "meta-data", {
        android("name"): "android.telephony.ims.MMTEL_FEATURE",
        android("value"): "true",
    })
    intent = ET.SubElement(service, "intent-filter")
    ET.SubElement(intent, "action", {android("name"): service_spec["action"]})
    application.append(service)


def _validate_result(tree: ET.ElementTree, contract: dict) -> None:
    root = tree.getroot()
    namespace = contract["input"]["android_namespace"]
    android = lambda name: _attr(namespace, name)
    applications = [child for child in root if child.tag == "application"]
    if len(applications) != 1:
        raise TransformError("post-validation application count mismatch")
    all_services = [element for element in tree.iter("service")
                    if element.get(android("name")) == contract["service"]["name"]]
    if len(all_services) != 1 or all_services[0] not in list(applications[0]):
        raise TransformError("post-validation target service count or parent mismatch")
    service = all_services[0]
    expected = {android("name"): contract["service"]["name"],
                android("permission"): contract["service"]["permission"],
                android("enabled"): "true", android("exported"): "true",
                android("singleUser"): "true"}
    if service.attrib != expected:
        raise TransformError("post-validation service attributes mismatch")
    actions = [element for element in service.iter("action")
               if element.get(android("name")) == contract["service"]["action"]]
    global_actions = [element for element in tree.iter("action")
                      if element.get(android("name")) == contract["service"]["action"]]
    if len(actions) != 1 or len(global_actions) != 1:
        raise TransformError("post-validation action count mismatch")
    metadata = [element for element in service.iter("meta-data")
                if element.get(android("name")) == "android.telephony.ims.MMTEL_FEATURE"]
    global_metadata = [element for element in tree.iter("meta-data")
                       if element.get(android("name")) == "android.telephony.ims.MMTEL_FEATURE"]
    if (len(metadata) != 1 or len(global_metadata) != 1 or
            metadata[0].attrib != {android("name"): "android.telephony.ims.MMTEL_FEATURE",
                                   android("value"): "true"}):
        raise TransformError("post-validation MMTEL metadata mismatch")
    for excluded in contract["excluded_features"]:
        if any(element.get(android("name")) == excluded for element in tree.iter("meta-data")):
            raise TransformError(f"post-validation excluded feature present: {excluded}")


def _safe_paths(source: Path, output: Path) -> tuple[Path, Path]:
    if source.is_symlink() or not source.is_file():
        raise TransformError("input must be a regular non-symlink file")
    source_resolved = source.resolve(strict=True)
    if output.is_symlink():
        raise TransformError("output must not be a symlink")
    parent = output.parent
    if parent.is_symlink() or not parent.is_dir():
        raise TransformError("output parent must be an existing non-symlink directory")
    output_resolved = parent.resolve(strict=True) / output.name
    if source_resolved == output_resolved:
        raise TransformError("input and output must be different paths")
    return source_resolved, output_resolved


def transform(contract_path: Path, source: Path, output: Path,
              allow_identical: bool = False) -> dict:
    contract = load_contract(contract_path)
    source, output = _safe_paths(source, output)
    source_data = source.read_bytes()
    tree = _parse_xml(source_data)
    application = _assert_source_shape(tree, contract)
    _insert(tree, application, contract)
    _validate_result(tree, contract)
    ET.register_namespace("android", contract["input"]["android_namespace"])
    rendered = ET.tostring(tree.getroot(), encoding="utf-8", xml_declaration=True)
    # Validate exactly what will be written, independently of the in-memory tree.
    _validate_result(_parse_xml(rendered), contract)
    if output.exists():
        if allow_identical and output.is_file() and output.read_bytes() == rendered:
            return {"transformation_id": contract["transformation_id"], "changed": False}
        raise TransformError(f"refusing to overwrite existing output: {output}")
    fd, temporary = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        # Linking a complete same-directory temporary file is atomic and, unlike
        # os.replace(), cannot overwrite a path created after our earlier check.
        os.link(temporary, output)
        os.unlink(temporary)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return {"transformation_id": contract["transformation_id"], "changed": True}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-identical", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = transform(args.contract, args.input, args.output, args.allow_identical)
    except (OSError, TransformError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
