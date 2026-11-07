"""Original 1.9 protocol primitives for a local compatibility server.

Wire format comes from original NetPacketV1, not the 7.0 server. Schema tags
come from generated original 1.9 protobuf serializers; provenance is retained
in server19_protocol_schema.json. This module performs no network operations.
"""
from dataclasses import dataclass
import json
from pathlib import Path
import struct
import zlib

HEAD_MAGIC = 0x01234567
TAIL_MAGIC = 0x89ABCDEF
HEADER = struct.Struct("!IHHIIIIIHIHI")
HEADER_SIZE = 40
TAIL_SIZE = 4
MAX_BODY_SIZE = 16 * 1024 * 1024
CRC32_SEED = 0xF0E1D2C3

_DATA = json.loads(Path(__file__).with_name("server19_protocol_schema.json").read_text(encoding="utf-8"))
CMD_IDS = {name.removeprefix("proto."): value for name, value in _DATA["commands"].items()}
CMD_NAMES = {value: name for name, value in CMD_IDS.items()}
SCHEMAS = _DATA["schemas"]

# These original writers each hold one EquipmentItemList, whose inner item_list
# is repeated. Field names alone do not establish protobuf cardinality.
# Evo33205, PowerUp33215, Sell33225, Title34249, Refine34581,
# Synthesis36338: one tag/write, no outer collection loop. Inner37370 loops.
_SINGLE_CONTAINER_FIELDS = frozenset({
    ("EquipmentEvoReq", "consume_item_list"),
    ("EquipmentPowerUpReq", "consume_item_list"),
    ("EquipmentSellReq", "sell_item_list"),
    ("LevelUpStigmataTitleReq", "consume_item_list"),
    ("RefineStigmataRuneReq", "consume_item_list"),
    ("EquipSynthesisRsp", "equip_list"),
})


@dataclass(frozen=True)
class Frame:
    cmd_id: int
    body: bytes = b""
    packet_version: int = 1
    client_version: int = 0
    time: int = 0
    user_id: int = 0
    user_ip: int = 0
    user_session_id: int = 0
    gateway_ip: int = 0
    sign_type: int = 0
    sign: int = 0

    @property
    def name(self):
        return CMD_NAMES.get(self.cmd_id, f"Unknown_{self.cmd_id}")


def encode_frame(cmd_id, body=b"", *, client_version=0, time=0, user_id=0,
                 user_ip=0, user_session_id=0, gateway_ip=0, sign_type=0):
    if isinstance(cmd_id, str):
        cmd_id = CMD_IDS[cmd_id.removeprefix("proto.")]
    body = bytes(body)
    if len(body) > MAX_BODY_SIZE:
        raise ValueError("body too large")
    return HEADER.pack(HEAD_MAGIC, 1, client_version, time, user_id, user_ip,
                       user_session_id, gateway_ip, cmd_id, len(body), sign_type,
                       zlib.crc32(body, CRC32_SEED) & 0xFFFFFFFF) + body + struct.pack("!I", TAIL_MAGIC)


def decode_frame(data, *, verify_crc=False):
    """Decode exactly one complete frame; reject partial or trailing input."""
    if len(data) < HEADER_SIZE:
        raise ValueError("incomplete header")
    (magic, version, cv, timestamp, uid, ip, session, gateway, cmd, length,
     sign_type, sign) = HEADER.unpack_from(data)
    if magic != HEAD_MAGIC or version != 1:
        raise ValueError("invalid original 1.9 frame header")
    if length > MAX_BODY_SIZE:
        raise ValueError("body too large")
    if len(data) != HEADER_SIZE + length + TAIL_SIZE:
        raise ValueError("incomplete or trailing frame data")
    body = bytes(data[HEADER_SIZE:HEADER_SIZE + length])
    if struct.unpack_from("!I", data, HEADER_SIZE + length)[0] != TAIL_MAGIC:
        raise ValueError("invalid tail magic")
    if verify_crc and zlib.crc32(body, CRC32_SEED) & 0xFFFFFFFF != sign:
        raise ValueError("CRC32 mismatch")
    return Frame(cmd, body, version, cv, timestamp, uid, ip, session, gateway, sign_type, sign)


def take_frames(buffer):
    """Consume complete frames from a mutable bytearray; keep partial input."""
    frames = []
    while len(buffer) >= HEADER_SIZE:
        header = HEADER.unpack_from(buffer)
        if header[0] != HEAD_MAGIC or header[1] != 1:
            raise ValueError("invalid original 1.9 frame header")
        body_len = header[9]
        if body_len > MAX_BODY_SIZE:
            raise ValueError("body too large")
        size = HEADER_SIZE + body_len + TAIL_SIZE
        if len(buffer) < size:
            break
        frames.append(decode_frame(buffer[:size]))
        del buffer[:size]
    return frames


def varint(value):
    value = int(value)
    if value < 0:
        value &= 0xFFFFFFFFFFFFFFFF
    out = bytearray()
    while value > 0x7F:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def read_varint(data, offset=0):
    value = 0
    for shift in range(0, 70, 7):
        if offset >= len(data):
            raise ValueError("truncated varint")
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, offset
    raise ValueError("invalid varint")


def wire_fields(data):
    """Read protobuf fields preserving repeats and unknown field bytes."""
    out = []
    at = 0
    while at < len(data):
        key, at = read_varint(data, at)
        tag, wire = key >> 3, key & 7
        if not tag:
            raise ValueError("invalid protobuf field zero")
        if wire == 0:
            value, at = read_varint(data, at)
        elif wire in (1, 5):
            size = 8 if wire == 1 else 4
            if at + size > len(data):
                raise ValueError("truncated fixed protobuf field")
            value = bytes(data[at:at + size])
            at += size
        elif wire == 2:
            size, at = read_varint(data, at)
            if at + size > len(data):
                raise ValueError("truncated length protobuf field")
            value = bytes(data[at:at + size])
            at += size
        else:
            raise ValueError(f"unsupported protobuf wire type {wire}")
        out.append((tag, wire, value))
    return out


def schema(name):
    if not name.startswith("proto."):
        name = "proto." + name
    return SCHEMAS[name]


def encode_message(name, values):
    # Original enum metadata fields 7752..7754 and reader 35362 accept 1..3 only.
    if name.removeprefix('proto.') == 'EndlessWarInfo' and values.get('type') not in (1, 2, 3):
        raise ValueError('EndlessWarInfo.type must be USE_ITEM=1, BOMB_CANCEL=2 or BOMB_BURST=3')
    fields = {f["name"]: f for f in schema(name)["fields"]}
    unknown = set(values) - set(fields)
    if unknown:
        raise ValueError(f"fields absent from original 1.9 {name}: {sorted(unknown)}")
    out = bytearray()
    for key, value in values.items():
        if value is None:
            continue
        f = fields[key]
        for item in value if isinstance(value, (list, tuple)) else [value]:
            out.extend(varint(f["tag"] << 3 | f["wire"]))
            if f["wire"] == 0:
                out.extend(varint(item))
            elif f["wire"] == 2:
                if isinstance(item, dict):
                    if "message" not in f:
                        raise ValueError(f"unresolved nested message {name}.{key}")
                    payload = encode_message(f["message"], item)
                elif isinstance(item, str):
                    payload = item.encode("utf-8")
                else:
                    payload = bytes(item)
                out.extend(varint(len(payload)))
                out.extend(payload)
            elif f["wire"] == 5:
                out.extend(struct.pack("<f" if f.get("writer") == "WriteSingle" else "<I", item))
            elif f["wire"] == 1:
                out.extend(struct.pack("<d" if f.get("writer") == "WriteDouble" else "<Q", item))
            else:
                raise ValueError(f"unsupported wire type {f['wire']}")
    return bytes(out)


def _merge_single_container(previous, current):
    """Original EquipmentItemList.ReadFrom appends its repeated item_list.

    The six audited parents reuse their existing container on a repeated tag,
    rather than changing the parent field to a list of containers.
    """
    for key, value in current.items():
        if key == 'item_list':
            previous.setdefault(key, []).extend(value)
        else:
            previous[key] = value
    return previous


def decode_message(name, data):
    fields = {f["tag"]: f for f in schema(name)["fields"]}
    out = {}
    for tag, wire, value in wire_fields(data):
        f = fields.get(tag)
        key = f["name"] if f else f"unknown_{tag}"
        if f:
            if wire == 2 and "message" in f:
                value = decode_message(f["message"], value)
            elif wire == 2 and f.get("writer") == "WriteString":
                value = value.decode("utf-8", errors="replace")
            elif wire == 0 and f.get("writer") == "WriteBoolean":
                value = bool(value)
            elif wire == 0 and f.get("writer") == "WriteInt32" and value & 0x80000000:
                value = (value & 0xFFFFFFFF) - 0x100000000
            elif wire == 5:
                value = struct.unpack("<f" if f.get("writer") == "WriteSingle" else "<I", value)[0]
            elif wire == 1:
                value = struct.unpack("<d" if f.get("writer") == "WriteDouble" else "<Q", value)[0]
        single_container = (name.removeprefix('proto.'), key) in _SINGLE_CONTAINER_FIELDS
        if single_container and key in out:
            out[key] = _merge_single_container(out[key], value)
        elif key.endswith("_list") and not single_container:
            out.setdefault(key, []).append(value)
        elif key in out:
            if not isinstance(out[key], list):
                out[key] = [out[key]]
            out[key].append(value)
        else:
            out[key] = value
    return out
