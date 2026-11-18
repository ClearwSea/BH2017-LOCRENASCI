"""Explicit, copy-on-write save-editor progression operations.

Catalogs are supplied by the caller from the running version's tables.  This
module never creates battle settlement or reward receipts.  stage_editor_stars
is an editor entitlement consumed only by the stage unlock-star gate.
"""
from copy import deepcopy
import time


def catalog_from_configured_runtime():
    """Extract editable catalogs after server19_portable.configure has run.

    The source is the deployed, capability-checked server configuration, not a
    bundled copy of private game data. Display names use its selected textmap.
    """
    import server19_stage as stage
    import server19_openworld as openworld
    import server19_extra_story as extra
    import server19_endless as endless
    if openworld._CATALOG is None or extra._CONFIG is None or endless.CATALOG is None:
        raise ValueError('运行时关卡目录尚未配置')
    extra_ids = set(extra._CONFIG['ids'])
    areas_by_id = {r['areaId']: r for r in extra._CONFIG['areas']}
    chapters_by_id = {r['chapterId']: r for r in extra._CONFIG['chapters']}
    extra_chapters = {}
    for act in extra._CONFIG['acts']:
        area = areas_by_id.get(act['areaId'])
        if not area or area['chapterId'] not in chapters_by_id:
            raise ValueError('外传关卡目录缺少章节或区域')
        chapter = chapters_by_id[area['chapterId']]
        for identity in act['stageIdList']:
            if identity in extra_chapters and extra_chapters[identity] != chapter:
                raise ValueError('外传关卡对应多个章节')
            extra_chapters[identity] = chapter
    story_ids = set(stage.STORY_CATALOG_STAGE_IDS)
    supported = set(stage.supported_stage_ids())
    texts = {row.get('ID'): row.get('Text') for row in stage._table('textmap')}
    rows = []
    for identity in sorted((story_ids | extra_ids) & supported):
        row = stage.stage_config(identity)
        row['id'] = identity
        row['kind'] = 'extra' if identity in extra_ids else 'story'
        if identity in extra_ids:
            if identity not in extra_chapters:
                raise ValueError('外传关卡缺少章节归属')
            chapter = extra_chapters[identity]
            row['editor_chapter_id'] = chapter['chapterId']
            row['editor_min_level'] = chapter['minPlayerLevel']
        else:
            row['editor_chapter_id'] = row['chapterId']
        name = row.get('name')
        row['display_name'] = texts.get(name, name) or str(identity)
        rows.append(row)
    if not rows:
        raise ValueError('运行时没有可用的剧情关卡')
    return {'stages': rows, 'sakura': deepcopy(openworld._CATALOG),
            'abyss_floors': endless.CATALOG['floors']}


def _integer(value, label, low=None, high=None):
    if type(value) is not int or (low is not None and value < low) or (high is not None and value > high):
        raise ValueError(label + '不在允许范围内')
    return value


def _stages(catalog):
    rows = catalog.get('stages')
    if not isinstance(rows, list) or not rows:
        raise ValueError('缺少当前版本的关卡目录')
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('关卡目录格式错误')
        identity = _integer(row.get('id', row.get('levelId')), '关卡 ID', 1)
        if identity in result:
            raise ValueError('关卡目录包含重复 ID')
        for key in ('chapterId', 'difficulty', 'unlockPlayerLevel', 'unlockStarNum', 'maxProgress'):
            _integer(row.get(key), '关卡 ' + key, 0)
        if not isinstance(row.get('preLevelID'), list) or not isinstance(row.get('challengeList'), list):
            raise ValueError('关卡前置条件或星级目录格式错误')
        result[identity] = row
    return result


def _stage_records(account):
    rows = account.get('stage_list')
    runtime = account.setdefault('stage_runtime', {'schema': 1, 'active': None, 'settlements': []})
    if (not isinstance(rows, list) or not isinstance(runtime, dict) or runtime.get('schema') != 1 or
            not isinstance(runtime.get('settlements'), list) or runtime.get('active') is not None):
        raise ValueError('关卡存档格式错误，或仍有进行中的关卡')
    if any(not isinstance(r, dict) or type(r.get('id')) is not int for r in rows):
        raise ValueError('关卡存档格式错误')
    saved = {r['id']: r for r in rows}
    if len(saved) != len(rows):
        raise ValueError('关卡存档包含重复 ID')
    return saved


def _empty_stage(identity):
    return dict(id=identity, progress=0, enter_times=0, reset_times=0,
                assist_enter_times=0, challenge_index_list=[], stamina_discount=100, is_done=False)


def _set_stars(account, saved, config, identity, desired):
    row = saved.get(identity)
    if row is None:
        row = _empty_stage(identity)
        account['stage_list'].append(row)
        saved[identity] = row
    indices = row.get('challenge_index_list', [])
    count = len(config['challengeList'])
    if (not isinstance(indices, list) or len(set(indices)) != len(indices) or
            any(type(i) is not int or not 0 <= i < count for i in indices)):
        raise ValueError('关卡星级与当前表不一致')
    row['challenge_index_list'] = sorted(set(indices) | set(desired))
    # This is distinct from a settlement: it only authorizes counting edited stars.
    account.setdefault('stage_editor_stars', {})[str(identity)] = list(row['challenge_index_list'])


def _wins(account):
    runtime = account['stage_runtime']
    receipts = runtime.get('settlements', [])
    if not isinstance(receipts, list):
        raise ValueError('关卡结算记录格式错误')
    wins = set()
    for receipt in receipts:
        if not isinstance(receipt, dict) or not isinstance(receipt.get('response', {}), dict):
            raise ValueError('关卡结算记录格式错误')
        response = receipt.get('response', {})
        if receipt.get('end_status') == 1 and response.get('retcode') == 0 and response.get('progress') == 1:
            wins.add(receipt.get('stage_id'))
    return wins


def _count_stars(account, saved, configs, chapter, difficulty):
    wins = _wins(account)
    edited = account.get('stage_editor_stars', {})
    if not isinstance(edited, dict):
        raise ValueError('编辑器星级记录格式错误')
    total = 0
    for identity, row in saved.items():
        cfg = configs.get(identity)
        if not cfg or (cfg['chapterId'], cfg['difficulty']) != (chapter, difficulty):
            continue
        stars = row.get('challenge_index_list', [])
        if not isinstance(stars, list) or any(type(i) is not int or not 0 <= i < len(cfg['challengeList']) for i in stars):
            raise ValueError('关卡星级与当前表不一致')
        approved = edited.get(str(identity), [])
        if not isinstance(approved, list) or any(type(i) is not int or not 0 <= i < len(cfg['challengeList']) for i in approved):
            raise ValueError('编辑器星级记录格式错误')
        eligible = set(stars) if identity in wins and row.get('is_done') and row.get('progress', 0) >= cfg['maxProgress'] else set(stars) & set(approved)
        total += len(eligible)
    return total


def _unlock(account, catalog, identity):
    configs = _stages(catalog)
    if identity not in configs:
        raise ValueError('该关卡不在当前版本可编辑目录中')
    saved = _stage_records(account)
    order = list(configs)
    level = _integer(account.get('main', {}).get('level'), '舰长等级', 1)
    visiting = set()
    prepared = set()

    def prepare(stage_id, complete):
        if stage_id not in configs:
            raise ValueError('关卡目录缺少必要前置关卡')
        if stage_id in visiting:
            raise ValueError('关卡前置关系存在循环')
        cfg = configs[stage_id]
        required = max(cfg['unlockPlayerLevel'], cfg.get('editor_min_level', 0))
        if level < required:
            raise ValueError('舰长等级不足，需要达到 %d 级' % required)
        if stage_id in prepared:
            if complete:
                saved[stage_id]['progress'] = max(saved[stage_id].get('progress', 0), cfg['maxProgress'])
                saved[stage_id]['is_done'] = True
            return
        visiting.add(stage_id)
        try:
            for prerequisite in cfg['preLevelID']:
                if prerequisite:
                    _integer(prerequisite, '前置关卡 ID', 1)
                    prepare(prerequisite, True)
            need = cfg['unlockStarNum']
            for candidate in order[:order.index(stage_id)]:
                if _count_stars(account, saved, configs, cfg['chapterId'], cfg['difficulty']) >= need:
                    break
                source = configs[candidate]
                if (candidate in visiting or (source['chapterId'], source['difficulty']) !=
                        (cfg['chapterId'], cfg['difficulty']) or not source['challengeList']):
                    continue
                # Candidate eligibility is checked recursively, exactly as for the target.
                prepare(candidate, True)
                have = _count_stars(account, saved, configs, cfg['chapterId'], cfg['difficulty'])
                missing = max(0, need - have)
                available = [i for i in range(len(source['challengeList']))
                             if i not in saved[candidate].get('challenge_index_list', [])]
                _set_stars(account, saved, source, candidate, available[:missing])
            if _count_stars(account, saved, configs, cfg['chapterId'], cfg['difficulty']) < need:
                raise ValueError('当前目录不能安全满足该关卡的星级前置条件')
            if complete:
                row = saved.get(stage_id)
                if row is None:
                    row = _empty_stage(stage_id)
                    account['stage_list'].append(row)
                    saved[stage_id] = row
                row['progress'] = max(row.get('progress', 0), cfg['maxProgress'])
                row['is_done'] = True
                prepared.add(stage_id)
        finally:
            visiting.remove(stage_id)
    prepare(identity, False)
    return ['已满足关卡 %d 的前置条件，目标关原有进度保持不变' % identity]


def _max_stars(account, catalog, op):
    configs = _stages(catalog)
    saved = _stage_records(account)
    chapter = _integer(op.get('chapter_id'), '章节', 0)
    difficulty = _integer(op.get('difficulty'), '难度', 0)
    kind = op.get('kind')
    selected = [(i, c) for i, c in configs.items() if c.get('editor_chapter_id', c['chapterId']) == chapter and
                c['difficulty'] == difficulty and (kind is None or c.get('kind') == kind)]
    if not selected:
        raise ValueError('该章节和难度没有可编辑关卡')
    level = _integer(account.get('main', {}).get('level'), '舰长等级', 1)
    if any(level < max(c['unlockPlayerLevel'], c.get('editor_min_level', 0)) for _, c in selected):
        raise ValueError('舰长等级不足以完成该章节')
    for identity, cfg in selected:
        _set_stars(account, saved, cfg, identity, range(len(cfg['challengeList'])))
        row = saved[identity]
        row.update(progress=max(row.get('progress', 0), cfg['maxProgress']), is_done=True)
    return ['已设置 %d 个关卡全部星级' % len(selected)]


def _sakura(account, catalog, op):
    source = catalog.get('sakura', {})
    stories = source.get('stories') if isinstance(source, dict) else None
    if not isinstance(stories, list):
        raise ValueError('缺少当前版本的轮回剧情目录')
    cycle = _integer(op.get('cycle'), '轮回', 1, 4)
    story = _integer(op.get('story_id'), '剧情 ID', 1)
    ordered = [r for r in stories if isinstance(r, dict) and type(r.get('Cycle')) is int and 1 <= r['Cycle'] <= 4]
    ordered.sort(key=lambda r: (r['Cycle'], r['StoryID']))
    ids = [r['StoryID'] for r in ordered]
    if len(ids) != len(set(ids)) or story not in ids or ordered[ids.index(story)]['Cycle'] != cycle:
        raise ValueError('轮回 PART 不在当前目录中')
    cycle_key = {1: 'cycle', 2: 'second_cycle', 3: 'third_cycle', 4: 'fourth_cycle'}[cycle]
    required = source.get(cycle_key, {}).get('level')
    if type(required) is not int or account.get('main', {}).get('level', 0) < required:
        raise ValueError('舰长等级不足以进入该轮回')
    world = account.get('openworld_data')
    runtime = account.get('openworld_runtime')
    if not isinstance(world, dict) or not isinstance(runtime, dict) or runtime.get('schema') != 1 or runtime.get('active') is not None:
        raise ValueError('请先进入过轮回并离开地图')
    finished, current, receipts = world.get('finish_story_id_list'), world.get('cur_story_list'), runtime.get('receipts')
    if not isinstance(finished, list) or not isinstance(current, list) or not isinstance(receipts, dict):
        raise ValueError('轮回剧情记录格式错误')
    if any(type(i) is not int for i in finished) or any(not isinstance(r, dict) or type(r.get('story_id')) is not int for r in current):
        raise ValueError('轮回剧情记录格式错误')
    if world.get('cycle', 0) not in (0, 1, 2, 3, 4):
        raise ValueError('当前存档超出可编辑的轮回范围')
    cycle_claims = world.get('has_take_finish_reward_cycle', 0)
    cycle_receipts = runtime.get('cycle_receipts', {})
    if type(cycle_claims) is not int or not 0 <= cycle_claims <= 4 or not isinstance(cycle_receipts, dict):
        raise ValueError('轮回结算领奖记录格式错误')
    for number in range(1, cycle_claims + 1):
        if str(number) not in cycle_receipts and not (number == 1 and runtime.get('cycle_receipt')):
            raise ValueError('已领取的轮回结算奖励缺少回执，无法安全修改')
    before = ids[:ids.index(story)]
    skipped = account.get('openworld_editor_skipped', [])
    if not isinstance(skipped, list) or any(type(i) is not int for i in skipped):
        raise ValueError('编辑器轮回记录格式错误')
    # Old saves without a receipt cannot establish whether a payout occurred.
    # Do not enable a potentially repeatable reward when rewinding those saves.
    if any(i in finished and receipts.get(str(i)) is None and i not in skipped
           for i in ids[ids.index(story):]):
        raise ValueError('部分已完成剧情缺少领奖记录，无法安全回退')
    skipped = list(dict.fromkeys(skipped + [i for i in before if i not in finished and receipts.get(str(i)) is None]))
    if skipped:
        account['openworld_editor_skipped'] = skipped
    # Unknown side stories are preserved; known selected/future stories become replayable.
    world['finish_story_id_list'] = list(dict.fromkeys([i for i in finished if i not in ids] + before))
    world['cur_story_list'] = [r for r in current if r['story_id'] not in ids]
    world['cycle'] = cycle
    world.pop('spawn_point', None)
    if 'area_teams' in runtime:
        runtime['area_teams'] = []
    # Never remove any existing story or cycle reward receipt.
    return ['轮回已切换至第 %d 轮剧情 %d，已有领奖记录保留' % (cycle, story)]


def _abyss(account, catalog, op, now):
    group = _integer(op.get('group'), '深渊段位', 1, 7)
    floors = _integer(catalog.get('abyss_floors'), '深渊层数', 1)
    floor = _integer(op.get('floor'), '深渊目标层', 1, floors)
    state = account.get('endless_runtime')
    if not isinstance(state, dict) or any(type(state.get(k)) is not int for k in ('begin', 'end', 'group', 'progress', 'max_progress')):
        raise ValueError('请先进入一次深渊并刷新本期数据')
    if account.get('main', {}).get('level', 0) < 25 or not state['begin'] <= now < state['end']:
        raise ValueError('深渊尚未解锁或本期数据已过期')
    if state.get('active') is not None or 'active' not in state:
        raise ValueError('请先结束深渊战斗')
    if not 1 <= state['group'] <= 7:
        raise ValueError('原深渊段位不在支持范围内')
    if state['group'] != group:
        state['group'] = group
        for key in ('display_temperature', 'climate_opponents', 'best_floor33_seconds'):
            state.pop(key, None)
        for key, value in (('wars', []), ('bot_penalties', {}), ('bombs', [])):
            if key in state:
                state[key] = value
    state['progress'] = floor - 1
    state['max_progress'] = max(state['max_progress'], state['progress'])
    state['progress_time'] = int(now)
    state['last_end'] = None
    # claimed_floors is deliberately preserved, including when moving backwards.
    return ['深渊已设置为段位 %d，从第 %d 层开始' % (group, floor)]


def apply(account, catalog, operation, now=None):
    """Return (edited independent account, change descriptions), or raise ValueError."""
    if not isinstance(account, dict) or not isinstance(catalog, dict) or not isinstance(operation, dict):
        raise ValueError('存档、目录或操作格式错误')
    result = deepcopy(account)
    op = operation.get('op')
    if op == 'story_unlock':
        changes = _unlock(result, catalog, _integer(operation.get('stage_id'), '关卡 ID', 1))
    elif op == 'story_max_stars':
        changes = _max_stars(result, catalog, operation)
    elif op == 'sakura_set_part':
        changes = _sakura(result, catalog, operation)
    elif op == 'abyss_set':
        changes = _abyss(result, catalog, operation, time.time() if now is None else now)
    else:
        raise ValueError('未知进度编辑操作')
    return result, changes
