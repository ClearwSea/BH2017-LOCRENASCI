"""Explicit offline GM configuration, applied on the next server start."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import time

CHINA = timezone(timedelta(hours=8))
BOSSES = (
    (1001, '帕凡提'), (201, '教父军团'), (3001, '卡莲'),
    (4001, '绯狱丸'), (501, 'RPC-6626'), (601, '阿湿波'),
    (701, '地藏御魂'), (8001, '被诅咒的英魂'), (9001, '影骑士·月轮'),
)
ALLOWED_BOSSES = frozenset(i for i, _ in BOSSES)
_CONFIG = {'schema': 1, 'abyss_temperature': None, 'exboss_overrides': {}}


def period(now):
    today = datetime.fromtimestamp(now, CHINA)
    begin = today.replace(hour=4, minute=0, second=0, microsecond=0)
    if today < begin:
        begin -= timedelta(days=1)
    begin -= timedelta(days=begin.weekday())
    return int(begin.timestamp()), int((begin + timedelta(days=7)).timestamp())


def _temperature(value):
    if value is not None and (type(value) is not int or not 0 <= value <= 180000):
        raise ValueError('深渊温度需为 0–180000 的整数')
    return value


def _bosses(value):
    if not isinstance(value, list) or len(value) != 3 or \
            any(type(i) is not int or i not in ALLOWED_BOSSES for i in value) or len(set(value)) != 3:
        raise ValueError('请选择三名不同的可用 Boss')
    return list(value)


def _validate(value):
    if not isinstance(value, dict) or set(value) != {'schema', 'abyss_temperature', 'exboss_overrides'} or \
            type(value['schema']) is not int or value['schema'] != 1:
        raise ValueError('服务端调整配置格式不正确')
    overrides = value['exboss_overrides']
    if not isinstance(overrides, dict):
        raise ValueError('记忆战场配置格式不正确')
    clean = {}
    for key, bosses in overrides.items():
        if not isinstance(key, str) or not key.isdigit():
            raise ValueError('记忆战场配置周期不正确')
        stamp = int(key)
        if period(stamp)[0] != stamp:
            raise ValueError('记忆战场配置周期不正确')
        clean[key] = _bosses(bosses)
    return {'schema': 1, 'abyss_temperature': _temperature(value['abyss_temperature']),
            'exboss_overrides': clean}


def _path(data_directory):
    return Path(data_directory) / 'gm-config.json'


def read(data_directory):
    path = _path(data_directory)
    if not path.exists():
        return {'schema': 1, 'abyss_temperature': None, 'exboss_overrides': {}}
    return _validate(json.loads(path.read_text(encoding='utf-8')))


def describe(data_directory, now=None):
    now = time.time() if now is None else now
    config = read(data_directory)
    _, next_begin = period(now)
    return {'abyss_temperature': config['abyss_temperature'],
            'next_bosses': deepcopy(config['exboss_overrides'].get(str(next_begin))),
            'effective_begin': next_begin,
            'bosses': [{'id': identity, 'name': name} for identity, name in BOSSES],
            'temperature_min': 0, 'temperature_max': 180000}


def save(data_directory, values, expected_effective_begin, now=None):
    """Write next period only; preserve a previously selected current period."""
    now = time.time() if now is None else now
    if not isinstance(values, dict) or set(values) != {'abyss_temperature', 'next_bosses'}:
        raise ValueError('服务端调整参数格式不正确')
    temperature = _temperature(values['abyss_temperature'])
    selected = None if values['next_bosses'] is None else _bosses(values['next_bosses'])
    current, next_begin = period(now)
    if type(expected_effective_begin) is not int or expected_effective_begin != next_begin:
        raise ValueError('记忆战场已进入新周期，请重新读取后再保存')
    previous = read(data_directory)
    overrides = {key: value for key, value in previous['exboss_overrides'].items() if int(key) >= current}
    if selected is None:
        overrides.pop(str(next_begin), None)
    else:
        overrides[str(next_begin)] = selected
    value = _validate({'schema': 1, 'abyss_temperature': temperature, 'exboss_overrides': overrides})
    path = _path(data_directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.gm-', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return describe(data_directory, now)


def configure(data_directory):
    global _CONFIG
    _CONFIG = read(data_directory)


def temperature_override():
    return _CONFIG['abyss_temperature']


def bosses_for_period(begin):
    return deepcopy(_CONFIG['exboss_overrides'].get(str(begin)))
