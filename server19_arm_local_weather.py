"""User-approved random local weather through original WeatherInfo callbacks.

Replace only WeatherInfoProvider.QueryWeatherInfo. Generic WWW timeout,
QA upload and all unrelated requests retain their original code.
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
import hashlib
import json
from pathlib import Path
import struct
import server19_arm_native as n
from server19_arm_resources import module_base

ROOT=Path(__file__).resolve().parent


def build(source, output):
    source,output=Path(source).resolve(),Path(output).resolve()
    assert source.is_relative_to(ROOT) and output.is_relative_to(ROOT) and not output.exists()
    output.mkdir(parents=True)
    image=n.ArmImage(source,expected_sha256=None)
    original=n.ArmImage()
    entry=image.method_code_addr(73673)
    assert image.read(entry,16)==original.read(entry,16)
    def slot(add_pc, first, second):
        return (add_pc+8+struct.unpack('<I',image.read(first,4))[0]+
                struct.unpack('<I',image.read(second,4))[0])&0xffffffff
    slots=dict(
        init_weather=slot(0x1630570,0x16307f4,0x16307f8),
        weather_class=slot(0x1630594,0x16307fc,0x1630800),
        init_callback=slot(0x16302f4,0x1630390,0x1630394),
        invoke_method=slot(0x1630364,0x1630398,0x163039c))
    for field,offset in [('temperature',8),('weatherType',12),('extraInfo',16),('infoTime',24)]:
        assert image.field_offset('MoleMole.WeatherInfo',field)==offset
    helper=image.allocate_code('approved local random weather provider',1024,
                               unwind=n.unwind_for_push(0x4070))
    c=n.ArmCode(helper);c.push(0x4070);c.mov(4,1);module_base(c,6)
    c.emit(0xe3540000);c.branch('null',cond='eq')
    def load_slot(reg,name):
        c.immediate(reg,slots[name]);c.emit(0xe0860000|(reg<<12)|reg)
        c.load(reg,reg);c.load(reg,reg)
    for name in ('init_weather','init_callback'):
        load_slot(0,name);c.call(0x42e020)
    load_slot(0,'weather_class');c.call(0x42e08c);c.mov(5,0)
    c.immediate(1,0);c.call(image.method_code_addr(73668))
    c.immediate(0,1);c.immediate(1,8);c.immediate(2,0)
    c.call(image.method_code_addr(18456));c.store(0,5,12)
    c.emit(0xe3500005);c.branch('snow',cond='eq')
    c.immediate(0,5);c.immediate(1,31);c.branch('temperature')
    c.label('snow');c.immediate(0,0xfffffff6);c.immediate(1,1)
    c.label('temperature');c.immediate(2,0);c.call(image.method_code_addr(18456))
    c.emit(0xee000a10);c.emit(0xeeb80ac0);c.emit(0xee100a10);c.store(0,5,8)
    # Original manager success callback stamps infoTime and updates the native
    # weather manager. Delegate method info is the original Action<WeatherInfo>.
    load_slot(2,'invoke_method');c.mov(0,4);c.mov(1,5);c.call(0x17dd448)
    c.pop(0x8070)
    c.label('null');c.call(0x42e0a4);c.pop(0x8070)
    code=c.finish();image.patch(helper,bytes(len(code)),code,'Return approved random WeatherInfo without WWW or Java threads')
    image.patch(entry,image.read(entry,16),n.arm_pic_jump(entry,helper),'Replace weather provider request only; keep original manager callbacks')
    dest=output/'libil2cpp.so';image.save(dest)
    report=dict(status='prepared_human_pending',source=str(source),entry=entry,helper=helper,
        helper_bytes=len(code),slots=slots,original_weather_values={'Sunny':1,'Cloudy':2,'HeavyCloudy':3,'Rainy':4,'Snowy':5,'Windy':6,'Lightning':7},
        weather_range=[1,8],temperature_range=[5,31],snow_temperature_range=[-10,1],
        random_api=image.method_code_addr(18456),constructor=image.method_code_addr(73668),
        invoke_api=0x17dd448,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),
        generic_www_and_qa_unchanged=True,account_untouched=True,human_acceptance='pending')
    (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    return report


if __name__=='__main__':
    import sys
    print(json.dumps(build(*sys.argv[1:])))
