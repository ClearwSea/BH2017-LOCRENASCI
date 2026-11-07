"""Extract command IDs and protobuf wire fields from the original 1.9 x86 image.

This is a static analysis helper. It does not run the client or reference server.
"""
from pathlib import Path
import json
import struct
import analyze19 as a

ROOT = Path(__file__).resolve().parent
BYVAL = {t[3]: i for i, t in enumerate(a.T)}


def fullname(ti):
    t = a.T[ti]
    if t[5] in BYVAL:
        return fullname(BYVAL[t[5]]) + "." + a.string(t[0])
    return a.type_name(ti)


def method_type(mi):
    m = a.M[mi]
    if not m[15]:
        return None
    p = struct.unpack_from("<4I", a.B, 7818260 + m[3] * 16)
    return BYVAL.get(p[3])


def instructions(mi):
    start = a.pointer(a.M[mi])
    if not start:
        return []
    end = min((p for p in a.ADDR if p > start), default=start + 50000)
    return list(a.MD.disasm(a.E[start:end], start))


def extract():
    defaults = {}
    for at in range(7483036, 7483036 + 162924, 12):
        fi, typ, off = struct.unpack_from("<3i", a.B, at)
        defaults[fi] = (typ, off)
    commands = {}
    for ti, t in enumerate(a.T):
        if a.type_name(ti) != "CmdId" or t[5] not in BYVAL:
            continue
        parent = BYVAL[t[5]]
        if not fullname(parent).startswith("proto."):
            continue
        fi = t[16] + 1
        value = struct.unpack_from("<i", a.B, 7645960 + defaults[fi][1])[0]
        commands[fullname(parent)] = value
    method_by_addr = {a.pointer(m): i for i, m in enumerate(a.M) if a.pointer(m)}
    schemas = {}
    for mi, m in enumerate(a.M):
        if a.string(m[0]) != "Write" or not a.type_name(m[1]).startswith("proto.ProtobufSerializer") or m[15] != 2:
            continue
        ti = method_type(mi)
        if ti is None:
            continue
        typename = fullname(ti)
        fields = {}
        getter = None
        active = None
        stack4 = None
        stack8 = None
        for ins in instructions(mi):
            if ins.mnemonic == "mov":
                parts = ins.op_str.split(", ")
                if len(parts) == 2:
                    dest, source = parts
                    try:
                        value = int(source, 0)
                    except ValueError:
                        value = None
                    if dest == "dword ptr [esp + 4]":
                        stack4 = value
                    elif dest == "dword ptr [esp + 8]":
                        stack8 = value
            if ins.mnemonic != "call" or not ins.op_str.startswith("0x"):
                continue
            addr = int(ins.op_str, 16)
            callee = a.ADDR.get(addr, "")
            if callee.startswith(a.type_name(ti) + "::get_") and not callee.endswith("Specified"):
                getter = callee.split("::get_", 1)[1]
            if callee == "ProtoBuf.ProtoWriter::WriteFieldHeader":
                if getter and stack4 is not None and stack8 is not None:
                    active = {"name": getter, "tag": stack4, "wire": stack8, "header_address": hex(ins.address)}
                    fields[getter] = active
                else:
                    active = None
            elif active and callee.startswith("ProtoBuf.ProtoWriter::Write") and "Header" not in callee:
                active["writer"] = callee.split("::", 1)[1]
            elif active and callee.endswith("::Write") and addr in method_by_addr:
                cti = method_type(method_by_addr[addr])
                if cti is not None:
                    active["message"] = fullname(cti)
                    active["writer"] = "WriteMessage"
        schemas[typename] = {"method_index": mi, "method_address": hex(a.pointer(m)), "fields": sorted(fields.values(), key=lambda x: x["tag"])}
    return {"source": "original 1.9.0 x86 IL2CPP", "commands": commands, "schemas": schemas}


if __name__ == "__main__":
    result = extract()
    path = ROOT / "server19_protocol_schema.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(result['commands'])} command IDs and {len(result['schemas'])} schemas to {path}")
