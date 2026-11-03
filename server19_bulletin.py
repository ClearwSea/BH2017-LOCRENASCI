"""Bulletin and holographic bridge banner service for Server 19.

Delivers holographic bridge banner bulletins (type=2) to activate
BeamProjectorBanner on the bridge and allow control panel switching.
Keeps bridge banners separate from the two native announcement tabs.
"""
import time

HANDLED_REQUESTS = frozenset(("GetBulletinReq",))

ANNOUNCEMENT_CONTENT = (
    "本游戏所展示内容为个人研究、学习及怀旧记录用途下进行的"
    "<color=#FFD78AFF>非官方本地化恢复版本</color>，版权归属米哈游。\n\n"
    "<color=#00C3FFFF>版本说明：</color>\n"
    "1. 完成了单APK化\n"
    "2. 恢复了剧情功能\n"
    "3. 恢复了多数外传\n"
    "4. 恢复了深渊（规则详见具体）\n"
    "5. 恢复了完整舰桥功能\n\n"
    "——来自 <color=#00C3FFFF>GITHUB/ClearwSea</color>\n"
    "鸣谢 Hssssssssi，以及各位AI。"
)


def response(name, account, values=None, *, account_path=None):
    if name not in HANDLED_REQUESTS:
        return None

    now = int(time.time())
    banner_ziyuan = {
        "id": 1,
        "type": 2,  # Banner bulletin type recognized by MonoBannerManager
        "weight": 90,
        "title_button": "前往",
        "title": "GitHub",
        "banner_path": "Server19/Bridge/Github",
        "event_date_str": time.strftime("%Y-%m-%d"),
        "content": "GitHub.com/ClearwSea",
        "mark": 0,
        "begin_time": now - 86400 * 30,
        "end_time": now + 86400 * 365,
        "update_time": now,
    }

    banner_standard = {
        "id": 2,
        "type": 2,
        "weight": 100,
        "title_button": "前往",
        "title": "2017庆典",
        "banner_path": "Server19/Bridge/Celebration",
        "event_date_str": time.strftime("%Y-%m-%d"),
        "content": "崩坏3 2017",
        "mark": 0,
        "begin_time": now - 86400 * 30,
        "end_time": now + 86400 * 365,
        "update_time": now,
    }

    # Original BulletinModule: event=0, system=1, holographic banner=2.
    # Supply content explicitly; the native body supports Unity rich text.
    announcements = [dict(
        id=201701 + show_type, type=show_type, weight=100,
        title_button="V1.9离线版说明", title="", event_date_str="", content=ANNOUNCEMENT_CONTENT,
        banner_path="Server19/Announcement/TeaParty", mark=0,
        begin_time=1767225600, end_time=2145916800, update_time=1793098800,
    ) for show_type in (0, 1)]
    bulletins = announcements + [banner_standard, banner_ziyuan]
    whole = int((values or {}).get("type", 1)) in (0, 1)
    if not whole:
        requested_ids = set((values or {}).get("bulletin_id_list", []))
        bulletins = [b for b in bulletins if b["id"] in requested_ids]

    return "GetBulletinRsp", {
        "retcode": 0,
        "bulletin_list": bulletins,
        "is_all": whole,
    }
