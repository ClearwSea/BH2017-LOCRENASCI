"""Build the bounded native-network experiment from the pristine 1.9 library.

Dispatch inputs, configuration supply, diagnostics and malformed gyro input
change. Original navigation remains intact; device acceptance is separate.
"""

import sys as _bh3_sys
from pathlib import Path as _Bh3Path
_bh3_source_root = _Bh3Path(__file__).resolve().parent
if _bh3_source_root.name == "scripts":
    _bh3_source_root = _bh3_source_root.parent
if str(_bh3_source_root) not in _bh3_sys.path:
    _bh3_sys.path.insert(0, str(_bh3_source_root))
from bh3_reference_guard import require_reference_mode as _require_reference_mode
_require_reference_mode(__name__)
from pathlib import Path
import argparse
import hashlib
import json

import server19_baked
import server19_baked_trace
import server19_client_patch
import server19_gyro_guard
import server19_metadata
import server19_json_resources
import server19_restart_trace
import server19_text_loader
import server19_trace

ROOT = Path(__file__).resolve().parent
RUN = ROOT / "server19-run"


def changed_ranges(before, after):
    """Group nearby binary edits; unchanged bytes in each range remain audited."""
    assert len(after) >= len(before)
    ranges = []
    start = last = None
    for offset, (old, new) in enumerate(zip(before, after)):
        if old == new:
            continue
        if start is None:
            start = offset
        elif offset - last > 16:
            ranges.append((start, last + 1))
            start = offset
        last = offset
    if start is not None:
        ranges.append((start, last + 1))
    return ranges


def build(*, trace_restarts=False, gyro_guard=True, output_directory=None):
    directory = RUN if output_directory is None else Path(output_directory).resolve()
    if not directory.is_relative_to(ROOT):
        raise ValueError("Build outputs must remain inside the project workspace")
    directory.mkdir(parents=True, exist_ok=True)
    dispatch = directory / "lib-server19-dispatch.so"
    trace = directory / "lib-server19-trace.so"
    text = directory / "lib-server19-text.so"
    output = directory / "lib-server19-resources.so"
    server19_client_patch.build(dispatch, "http://127.0.0.1:21018/query_dispatch")
    server19_trace.install(dispatch, trace)
    server19_text_loader.install(trace, text)
    before = text.read_bytes()
    binary = bytearray(before)
    resources = server19_baked.install(binary)
    tables = server19_metadata.install(binary)
    async_json = server19_json_resources.install(binary)
    packed_diagnostics = server19_baked_trace.install(binary)
    restart_diagnostics = (server19_restart_trace.install(binary) if trace_restarts else
                           {"enabled": False, "scope": "original RestartGame entry remains unchanged"})
    gyro_input_guard = (server19_gyro_guard.install(binary) if gyro_guard else
                       {"enabled": False, "scope": "original gyro input for controlled comparison"})
    manifest = json.loads(text.with_suffix(".so.json").read_text(encoding="utf-8"))
    for start, end in changed_ranges(before, binary):
        manifest["changes"].append({"offset": hex(start), "size": end - start,
            "before": before[start:end].hex(), "after": binary[start:end].hex(),
            "purpose": "resource suppliers, diagnostics and gyro input guard; native startup/navigation retained"})
    if len(binary) > len(before):
        appended = binary[len(before):]
        manifest["changes"].append({"offset": hex(len(before)), "size": len(appended),
            "before": "", "after": appended.hex(),
            "purpose": "new RX gyro guard and mapped program headers; original method storage retained"})
    assert binary[0x5471DF:0x5471E3] == bytes.fromhex("c6 40 01 00")
    manifest["output_sha256"] = hashlib.sha256(binary).hexdigest()
    manifest["configuration_resources"] = resources
    manifest["typed_table_supplier"] = tables
    manifest["async_json_supplier"] = async_json
    manifest["packed_data_diagnostics"] = packed_diagnostics
    manifest["restart_diagnostics"] = restart_diagnostics
    manifest["gyro_input_guard"] = gyro_input_guard
    manifest["resource_manifests"] = []
    for directory in ("baked-fallback", "metadata-fallback", "resource-fallback"):
        path = ROOT / ".local-baseline/server19-dev" / directory / "manifest.json"
        if path.exists():
            contents = path.read_bytes()
            manifest["resource_manifests"].append({
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": hashlib.sha256(contents).hexdigest(),
                "scope": "build input inventory; device deployment verified separately"})
    original = server19_client_patch.ORIGINAL.read_bytes()
    assert binary[0xA648DD:0xA649F4] == original[0xA648DD:0xA649F4]
    manifest["preserved"] = [value for value in manifest["preserved"] if value != "resource loading"]
    manifest["preserved"].append("original configuration consumers and module initialization")
    manifest["verification"] = "build input and patch ranges checked; device acceptance pending"
    output.write_bytes(binary)
    output.with_suffix(".so.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "sha256": manifest["output_sha256"],
                      "baked_resources": len(resources["resources"]),
                      "metaconfig_fields": len(resources["metaconfig"]["field_names"])}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace-restarts", action="store_true",
                        help="log original restart callers without changing restart behavior")
    parser.add_argument("--no-gyro-guard", action="store_true",
                        help="retain original gyro input for controlled comparison")
    parser.add_argument("--output-directory", type=Path,
                        help="separate workspace directory for a candidate build")
    args = parser.parse_args()
    build(trace_restarts=args.trace_restarts, gyro_guard=not args.no_gyro_guard,
          output_directory=args.output_directory)
