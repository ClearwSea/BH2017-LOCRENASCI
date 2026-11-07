"""All five shared supply pools: immutable catalogs and scoped draw snapshots.

Only the verified draw/grant functions may run in the scoped snapshot region.
The outer response transaction still owns a full independent account copy.
"""
from functools import lru_cache, wraps
import marshal
import threading

DRAW_KEYS = ('main', 'material_list', 'weapon_list', 'stigmata_list',
             'avatar_list', 'gacha_runtime')


def install(stage, server=None):
    if getattr(stage, "_gacha_optimized", False):
        return
    stage._gacha_optimized = True
    import server19_fastcopy as fast
    import server19_gacha as gacha
    import server19_gacha_policy as policy

    # Portable tables are verified JSON trees; cold cache misses need not use
    # the Python generic copier before the existing immutable-table adapter.
    original_choices = policy.choices
    policy._uncached_choices = original_choices
    original_table = gacha._table_for

    @lru_cache(maxsize=4)
    def encoded_choices(channel):
        return marshal.dumps(original_choices(channel), 4)

    def choices(channel):
        return marshal.loads(encoded_choices(channel))

    # _table_for returns nested tuples/scalars, with no mutable descendants.
    cached_table = lru_cache(maxsize=5)(original_table)
    gacha._table_for = cached_table
    policy.choices = choices
    gacha._awakened_avatar_ids = lru_cache(maxsize=1)(gacha._awakened_avatar_ids)
    local = threading.local()
    original_draw = gacha._draw
    original_gcopy, original_pcopy = gacha.deepcopy, policy.deepcopy

    def scoped_copy(original):
        def copy(value, memo=None):
            if memo is None and value is getattr(local, 'account', None):
                # Every original mutation under _draw/_grant/commit touches
                # only these roots. Preserve root insertion order and share
                # only untouched history/configuration branches.
                result = value.copy()
                changed = {key: value[key] for key in DRAW_KEYS if key in value}
                result.update(fast.deepcopy(changed))
                return result
            return original(value) if memo is None else original(value, memo)
        return copy

    @wraps(original_draw)
    def draw(account, *args, **kwargs):
        previous = getattr(local, 'account', None)
        local.account = account
        try:
            return original_draw(account, *args, **kwargs)
        finally:
            local.account = previous

    gacha._draw = draw
    gacha.deepcopy = scoped_copy(original_gcopy)
    policy.deepcopy = scoped_copy(original_pcopy)
    return {'choices': encoded_choices.cache_info, 'tiers': cached_table.cache_info}
