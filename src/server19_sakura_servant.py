"""Fourth-cycle servant feeding using the original feed-preview level rules."""

def add_exp(account, values, catalog):
    world = account['openworld_data']
    if not catalog.get('fourth_cycle') or 405 not in world['finish_story_id_list']:
        return {'retcode': 1}
    identity, count = values.get('material_id'), values.get('material_num')
    if type(identity) is not int or type(count) is not int or count <= 0:
        return {'retcode': 1}
    config = next((r for r in catalog['servant_materials'] if r['ID'] == identity), None)
    owned = next((r for r in account.get('material_list', []) if r['id'] == identity), None)
    if config is None or owned is None or owned['num'] < count:
        return {'retcode': 1}
    levels = {r['Level']: r for r in catalog['servant_levels']}
    # Original CalculateLevelAfter76668 caps at max_quest_level, not its
    # weekly rolled-back current level; GetServantMaxLevel70292 reads table max.
    cap = min(max(levels), max(1, world['quest_data'].get('max_quest_level', 1)))
    level, exp = world['servant_level'], world['servant_exp']
    if level >= cap and exp >= levels[level]['Exp']:
        return {'retcode': 1}
    total = exp + config['ServantExpProvide'] * count
    while level < cap and total >= levels[level]['Exp']:
        total -= levels[level]['Exp']
        level += 1
    # At the adventure-level ceiling, the original preview still has an
    # EXP bar for that level. Do not silently discard overflowing materials.
    if level >= cap and total > levels[level]['Exp']:
        return {'retcode': 1}
    owned['num'] -= count
    world.update(servant_level=level, servant_exp=total)
    return {'retcode': 0}
