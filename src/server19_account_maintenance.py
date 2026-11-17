"""Transactional wallet invariant and four-o'clock runtime rollover."""
import server19_business_clock as clock

SCOIN_LIMIT = 100000000  # GetMiscData advertises this exact cap.


def normalize_gold(account):
    main = account.get('main', {})
    value = main.get('scoin', 0)
    if type(value) is not int or value < 0:
        raise ValueError('Invalid stored gold balance')
    if value > SCOIN_LIMIT:
        account.setdefault('wallet_limit_audit', []).append({
            'at': clock.local_now().timestamp(), 'currency': 'scoin',
            'before': value, 'after': SCOIN_LIMIT, 'overflow': value - SCOIN_LIMIT})
        main['scoin'] = SCOIN_LIMIT


def normalize(account, now=None):
    import server19_stage as stage
    import server19_duty as duty
    import server19_signin as signin
    import server19_shop as shop
    import server19_player_progression as progression
    normalize_gold(account)
    progression.reconcile_equipment_size_limit(account)
    if isinstance(account.get("material_list"), list):
        account["material_list"] = [m for m in account["material_list"] if m.get("num", 0) > 0]
    duty._runtime(account, now)
    signin._ensure_runtime(account, now)
    shop._get_shop_runtime(account, now)
    stage.rollover_stage_attempts(account, now)
