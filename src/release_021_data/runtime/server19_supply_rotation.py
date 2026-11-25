"""Reviewed historical UP themes projected onto the current offline rules."""
from copy import deepcopy

PRECISE, EXPANSION = 3, 5
LEGACY_KEYS = {PRECISE: 'focused:ziyuan-bloodembrace-dracula-v1',
               EXPANSION: 'expansion:ziyuan-20180112-local-v1'}
DEFAULTS = {PRECISE: 'P07', EXPANSION: 'E06'}
MARKS = {
    '叶卡捷琳娜': (30046, 30099, 30152),
    '塞西莉亚·沙尼亚特': (30461, 30465, 30469),
    '卡莲·誓约': (30404, 30408, 30412),
    '克列欧博克拉': (30034, 30087, 30140),
    '卡莲·颂歌': (30747, 30751, 30755),
    '莎士比亚': (30042, 30095, 30148),
}
PRECISE_ROWS = (
    ('P01', '1.1', '2016-11-18', '战场疾风', 20145, '尼德霍格翼爪', '叶卡捷琳娜'),
    ('P02', '1.4', '2017-04-28', '御神装·勿忘', 20410, '仿灵刀·冰昙天', '塞西莉亚·沙尼亚特'),
    ('P03', '1.5', '2017-06-02', '女武神·誓约', 20460, '犹大的誓约', '卡莲·誓约'),
    ('P04', '1.5', '2017-06-09', '处刑装·紫苑', 20464, '仿犹大·血之拥抱', '克列欧博克拉'),
    ('P05', '1.8', '2017-10-13', '神恩颂歌', 20479, '11th圣遗物', '卡莲·颂歌'),
    ('P06', '1.8', '2017-10-20', '真炎幸魂', 20586, '雨后誓言', '叶卡捷琳娜'),
    ('P07', '1.9', '2017-11-24', '圣仪装·今样', 20538, '异型·赫尔之弓', '莎士比亚'),
    ('P08', '1.9', '2017-11-27', '御神装·勿忘', 20410, '仿灵刀·冰昙天', '莎士比亚'),
)
EXPANSION_ROWS = (
    ('E01', '1.4', '2017-04-15', '御神装·勿忘', 60212, '逆神巫女', 60211),
    ('E02', '1.5', '2017-05-28', '处刑装·紫苑', 60502, '女武神·誓约', 60501),
    ('E03', '1.6', '2017-07-07', '处刑装·紫苑', 60502, '樱火轮舞', 60503),
    ('E04', '1.7', '2017-08-25', '异度黑核侵蚀', 60312, '银狼的黎明', 60311),
    ('E05', '1.8', '2017-10-13', '神恩颂歌', 60504, '真炎幸魂', 60213),
    ('E06', '1.9', '2017-11-24', '御神装·勿忘', 60212, '圣仪装·今样', 60112),
)

THEMES = {}
for key, version, date, armor, identity, weapon, mark in PRECISE_ROWS:
    items = [('weapon', identity, weapon)]
    items += [('stigmata', i, f'{mark}（{slot}）') for slot, i in zip('上中下', MARKS[mark])]
    THEMES[key] = dict(key=key, channel=PRECISE, version=version, date=date, armor=armor,
                       name=f'{weapon}＋{mark}', items=items)
for key, version, date, armor, s, name, a in EXPANSION_ROWS:
    THEMES[key] = dict(key=key, channel=EXPANSION, version=version, date=date, armor=armor,
                       name=f'{armor}＋{name}',
                       items=[('avatar_card', s, armor), ('avatar_card', a, name)])


def active(account, channel):
    if channel not in DEFAULTS:
        return None
    runtime = account.get('gacha_runtime', {})
    return runtime.get('rotation', {}).get(str(channel), DEFAULTS[channel])


def switch(account, channel, target, expected):
    if type(channel) is not int or channel not in DEFAULTS:
        raise ValueError('未知补给通道')
    if not isinstance(target, str) or target not in THEMES or THEMES[target]['channel'] != channel:
        raise ValueError('请选择该通道的补给主题')
    current = active(account, channel)
    if current != expected:
        raise ValueError('当前主题已变化，请重新读取补给轮换')
    if target == current:
        return
    import server19_gacha as gacha
    import server19_gacha_policy as policy
    policy.choices(channel, target)
    runtime = gacha._runtime(account)
    runtime.setdefault('rotation', {})[str(channel)] = target
    runtime.setdefault('refresh_after_switch', {})[str(channel)] = True
    gacha._gacha_random(account)


def catalog():
    return [{'key': theme['key'], 'channel': theme['channel'], 'version': theme['version'],
             'date': theme['date'], 'name': theme['name'], 'pool': [name for _, _, name in theme['items']]}
            for theme in THEMES.values()]


def describe(account):
    from server19_gacha_policy import state
    return {str(c): {'key': active(account, c), 'pity': {
        key: state(account, c)[key] for key in ('since_common', 'since_rare', 'since_up')}}
        for c in DEFAULTS}


def recent(account, page):
    if type(page) is not int or not 0 <= page < 20:
        raise ValueError('记录页码无效')
    rows = account.get('gacha_runtime', {}).get('log', [])
    start = page * 10
    return {'page': page, 'more': len(rows) > start + 10,
            'rows': [deepcopy(row) for row in rows[::-1][start:start + 10]]}
