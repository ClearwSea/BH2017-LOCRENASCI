"""A32 equivalent of the accepted x86 post-ConfigChannel dispatch input hook.

Calls the original deserializer first, with the same register arguments and
MethodInfo. Only already occupied DispatchUrls List<string> elements change.
Original SDK flags, transport, accounts, packet consumers and page flow stay
in their original methods. No fake login, debug branch, exception suppression,
device operation or gameplay operation is performed here.
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
import struct
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
ORIGINAL = ROOT / ".local-baseline/server19-dev/sony-arm-reference/armeabi-v7a/libil2cpp.so"
ORIGINAL_SHA256 = "32e27ed130ed3a2a8c23d81c6a043510ae6cd99bd34b4bea4da1d71abae6c7a6"
HOOK = 0x1285A90
ORIGINAL_DESERIALIZE = 0x2A38268
STRING_NEW_EXPORT = 0x2C3D518
DEFAULT_URL = "http://127.0.0.1:21018/query_dispatch"


def branch(position, target, *, link=False, condition=14):
    delta = target - position - 8
    if position & 3 or target & 3 or delta % 4 or not -(1 << 25) <= delta < (1 << 25):
        raise ValueError("A32 branch requires aligned addresses within32MiB")
    return struct.pack("<I", condition << 28 | (0x0B000000 if link else 0x0A000000) |
                       ((delta // 4) & 0xFFFFFF))


def _url(dispatch_url):
    parsed = urlsplit(dispatch_url)
    if parsed.scheme != "http" or not parsed.hostname or parsed.query or parsed.fragment or \
            parsed.username or parsed.password or "\0" in dispatch_url:
        raise ValueError("Use an explicit ASCII HTTP dispatch endpoint without credentials/query/fragment")
    return dispatch_url.encode("ascii") + b"\0"


def stub(cave, dispatch_url=DEFAULT_URL):
    """PIC A32 code, including long-range AAPCS calls through scratch ip.

    push4 registers keeps8-byte stack alignment. Both helper calls preserve
    argument registers until the call; scratch r12 is caller-saved. The delta
    literals are skipped on return and remain valid under ELF base relocation.
    """
    url = _url(dispatch_url)
    if cave & 3:
        raise ValueError("A32 cave must be4-byte aligned")
    code = bytearray()
    labels, jumps, calls, data = {}, [], [], []
    def emit(word):
        code.extend(struct.pack("<I", word))
    def jump(name, condition):
        jumps.append((len(code), name, condition))
        emit(0)
    def call(target):
        offset = len(code)
        # ldr ip,[pc,#8]; add ip,pc,ip; blx ip; b past delta; .word delta.
        emit(0xE59FC008)
        emit(0xE08FC00C)
        emit(0xE12FFF3C)
        code.extend(branch(cave + len(code), cave + offset + 20))
        emit((target - (cave + offset + 12)) & 0xFFFFFFFF)
        calls.append({"offset": offset, "target": target, "literal_offset": offset + 16,
                      "return_offset": offset + 12})
        data.append((offset + 16, offset + 20))

    emit(0xE92D4070)  # push{r4,r5,r6,lr}
    call(ORIGINAL_DESERIALIZE)
    emit(0xE1A04000)  # movr4,r0: preserve exact deserialized ConfigChannel result.
    emit(0xE3540000)  # cmpr4,#0
    jump("done", 0)
    emit(0xE5945018)  # ldrr5,[r4,#0x18]: original DispatchUrls List<string>.
    emit(0xE3550000)
    jump("done", 0)
    emit(0xE5956008)  # ldrr6,[r5,#8]: List._items
    emit(0xE3560000)
    jump("done", 0)
    emit(0xE595500C)  # ldrr5,[r5,#12]: List._size, retain capacity/version.
    url_adr = len(code)
    emit(0)
    call(STRING_NEW_EXPORT)
    emit(0xE3550000)  # cmpr5,#0
    jump("done", 0)
    emit(0xE2866010)  # addr6,r6,#16: managed string array element data
    labels["loop"] = len(code)
    emit(0xE2555001)  # subsr5,r5,#1
    emit(0xE7860105)  # strr0,[r6,r5,lsl#2]: occupied slots only.
    jump("loop", 1)
    labels["done"] = len(code)
    emit(0xE1A00004)  # movr0,r4
    emit(0xE8BD8070)  # pop{r4,r5,r6,pc}
    url_offset = len(code)
    displacement = url_offset - url_adr - 8
    if not 0 <= displacement <= 255:
        raise ValueError("URL exceeds the bounded ADR immediate")
    struct.pack_into("<I", code, url_adr, 0xE28F0000 | displacement)
    code.extend(url)
    while len(code) & 3:
        code.append(0)
    for offset, name, condition in jumps:
        code[offset:offset + 4] = branch(cave + offset, cave + labels[name], condition=condition)
    return bytes(code), {"labels": labels, "calls": calls, "literal_ranges": data,
                         "url_offset": url_offset, "url": dispatch_url,
                         "preserved_stack_alignment": 8, "saved_registers": ["r4", "r5", "r6", "lr"]}


def verify_stub(cave, dispatch_url=DEFAULT_URL):
    """Decode/step the emitted A32 subset with mocked native calls, no device.

    This checks PIC calls, register/stack ABI and every guarded list path. It
    does not execute Unity, establish native exception-unwind compatibility,
    or replace real bridge-entry acceptance.
    """
    code, layout = stub(cave, dispatch_url)
    scenarios = [("null_config", False, True, True, 3, 5),
                 ("null_list", True, False, True, 3, 5),
                 ("null_items", True, True, False, 3, 5),
                 ("empty_list", True, True, True, 0, 5),
                 ("one_of_five", True, True, True, 1, 5),
                 ("three_of_five", True, True, True, 3, 5)]
    checks = []
    for load_base in (0, 0x65000000):
        for name, has_config, has_list, has_items, count, capacity in scenarios:
            start = load_base + cave
            reg = [0x7000 + i * 16 for i in range(16)]
            reg[:4] = [0, 0x12345678, 0xABCDEF00, 0x11223344]
            reg[13], reg[14], reg[15] = 0x30001000, 0x12340000, start
            initial = reg.copy()
            config, urls, items, replacement = 0x10001000, 0x10002000, 0x10003000, 0x10004000
            memory = {config + 0x18: urls if has_list else 0,
                      urls + 8: items if has_items else 0,
                      urls + 12: count, urls + 16: 9876,
                      items + 12: capacity}
            for index in range(capacity):
                memory[items + 16 + index * 4] = 0x11000000 + index * 4
            before = dict(memory)
            calls, zero, steps = [], False, 0
            def read(address):
                offset = address - start
                if 0 <= offset <= len(code) - 4:
                    return struct.unpack_from("<I", code, offset)[0]
                if address not in memory:
                    raise AssertionError("Unexpected memory read at" + hex(address))
                return memory[address]
            while reg[15] != initial[14]:
                steps += 1
                assert steps <= 100
                pc = reg[15]
                word = read(pc)
                reg[15] = pc + 4
                condition = word >> 28
                if condition == 0 and not zero or condition == 1 and zero:
                    continue
                assert condition in (0, 1, 14)
                if word == 0xE92D4070:
                    reg[13] -= 16
                    for index, number in enumerate((4, 5, 6, 14)):
                        memory[reg[13] + index * 4] = reg[number]
                elif word == 0xE8BD8070:
                    for index, number in enumerate((4, 5, 6, 15)):
                        reg[number] = read(reg[13] + index * 4)
                    reg[13] += 16
                elif word & 0x0F000000 == 0x0A000000:
                    displacement = word & 0xFFFFFF
                    if displacement & 0x800000:
                        displacement -= 1 << 24
                    reg[15] = pc + 8 + displacement * 4
                elif word == 0xE59FC008:
                    reg[12] = read(pc + 16)
                elif word == 0xE08FC00C:
                    reg[12] = (pc + 8 + reg[12]) & 0xFFFFFFFF
                elif word == 0xE12FFF3C:
                    assert reg[13] % 8 == 0
                    target = reg[12]
                    calls.append(target - load_base)
                    reg[14] = pc + 4
                    if target == load_base + ORIGINAL_DESERIALIZE:
                        assert reg[:4] == initial[:4]
                        reg[0] = config if has_config else 0
                    elif target == load_base + STRING_NEW_EXPORT:
                        assert reg[0] == start + layout["url_offset"]
                        assert code[layout["url_offset"]:].split(b"\0", 1)[0] == dispatch_url.encode("ascii")
                        reg[0] = replacement
                    else:
                        raise AssertionError("Unexpected PIC call target")
                    # A real AAPCS call may freely clobber these registers.
                    reg[1], reg[2], reg[3], reg[12], zero = 99, 98, 97, 96, False
                elif word == 0xE1A04000:
                    reg[4] = reg[0]
                elif word == 0xE1A00004:
                    reg[0] = reg[4]
                elif word == 0xE3540000:
                    zero = reg[4] == 0
                elif word == 0xE3550000:
                    zero = reg[5] == 0
                elif word == 0xE3560000:
                    zero = reg[6] == 0
                elif word == 0xE5945018:
                    reg[5] = read(reg[4] + 0x18)
                elif word == 0xE5956008:
                    reg[6] = read(reg[5] + 8)
                elif word == 0xE595500C:
                    reg[5] = read(reg[5] + 12)
                elif word & 0xFFFFFF00 == 0xE28F0000:
                    reg[0] = pc + 8 + (word & 0xFF)
                elif word == 0xE2866010:
                    reg[6] += 16
                elif word == 0xE2555001:
                    reg[5] = (reg[5] - 1) & 0xFFFFFFFF
                    zero = reg[5] == 0
                elif word == 0xE7860105:
                    memory[reg[6] + reg[5] * 4] = reg[0]
                else:
                    raise AssertionError("Unsupported/executed-literal opcode" + hex(word))
            assert reg[0] == (config if has_config else 0)
            assert reg[4:12] == initial[4:12] and reg[13] == initial[13]
            assert calls == ([ORIGINAL_DESERIALIZE, STRING_NEW_EXPORT]
                             if has_config and has_list and has_items else [ORIGINAL_DESERIALIZE])
            changed_addresses = {items + 16 + index * 4 for index in range(count)} \
                if has_config and has_list and has_items else set()
            for address, value in before.items():
                assert memory[address] == (replacement if address in changed_addresses else value)
            checks.append({"scenario": name, "load_base": hex(load_base), "instructions": steps})
    return {"status": "PASS", "checks": checks, "native_runtime_acceptance": "pending",
            "scope": "emitted A32 instruction-subset stepping with mocked native calls"}


def install(image, dispatch_url=DEFAULT_URL):
    """Add to the shared ArmImage; root alone finalizes/saves the combined ELF."""
    import server19_arm_native as native
    if image.source_sha256 != ORIGINAL_SHA256:
        raise ValueError("Original ARM network source hash differs")
    start, end = image.method_range(72965)
    if start != 0x1285860 or not start <= HOOK < end:
        raise ValueError("Original NetworkManager constructor mapping differs")
    if image.symbol("il2cpp_string_new") != STRING_NEW_EXPORT:
        raise ValueError("Original ARM string constructor mapping differs")
    if image.field_offset("ConfigChannel", "DispatchUrls") != 0x18:
        raise ValueError("Original ARM DispatchUrls field layout differs")
    before = branch(HOOK, ORIGINAL_DESERIALIZE, link=True)
    if image.read(HOOK, 4) != before or image.read(HOOK + 4, 4) != struct.pack("<I", 0xE3500000):
        raise ValueError("Original ConfigChannel deserialization call/result guard differs")
    # No network-debug branch is enabled. Preserve the original zero store.
    if image.method(43292) != 0x56D7C0 or image.read(0x56D838, 4) != struct.pack("<I", 0xE5C17001):
        raise ValueError("Original GlobalVars network-debug initializer differs")
    size = len(stub(0, dispatch_url)[0])
    helper = image.allocate_code("network", size, unwind=0x80AAB0B0)
    code, layout = stub(helper, dispatch_url)
    verification = verify_stub(helper, dispatch_url)
    image.patch(helper, bytes(size), code, "post-original-ConfigChannel occupied DispatchUrls redirection")
    veneer = image.near_veneer(HOOK, helper, storage_mid=72868, name="network-zero-stack-PIC-tail")
    image.patch(HOOK, before, native.arm_branch(HOOK, veneer, link=True),
                "call original ConfigChannel deserializer through ARM input-only dispatch adapter")
    return {"source_sha256": image.source_sha256, "hook": hex(HOOK),
            "original_deserialize": hex(ORIGINAL_DESERIALIZE), "helper": hex(helper),
            "veneer": hex(veneer), "helper_size": size,
            "helper_sha256": hashlib.sha256(code).hexdigest(),
            "dispatch_url": dispatch_url, "stub_layout": layout,
            "unwind": {"compact": "0x80aab0b0", "operations": "pop r4,r5,r6,lr; finish",
                       "stack_bytes": 16, "original_LSDA_reused": False},
            "preserved": ["original ConfigChannel deserialization and MethodInfo",
                          "ConfigChannel instance and all SDK/account flags",
                          "DispatchUrls list size/capacity/version/unoccupied array elements",
                          "original NetworkManager/transport/packet/page flow",
                          "original network-debug=false initialization"],
            "verification": verification, "native_bridge_acceptance": "pending"}


def build(output, dispatch_url=DEFAULT_URL, source=ORIGINAL):
    """Standalone network-only candidate for static review; no deployment."""
    import server19_arm_native as native
    image = native.ArmImage(source)
    details = install(image, dispatch_url)
    image.finalize()
    manifest = image.save(Path(output))
    manifest["network"] = details
    Path(output).with_suffix(Path(output).suffix + ".json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return details


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--dispatch-url", default=DEFAULT_URL)
    parser.add_argument("--source", type=Path, default=ORIGINAL)
    arguments = parser.parse_args()
    result = build(arguments.output, arguments.dispatch_url, arguments.source)
    print(json.dumps(result, indent=2))
