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
    "<color=#FF4040FF>1.详见左侧更新公告</color>\n\n"
    "——来自 <color=#00C3FFFF>GITHUB/ClearwSea</color>\n"
    "鸣谢 Hssssssssi，以及各位AI。"
)


UPDATE_CONTENT = '<color=#FF4040FF>当前版本为V0.1.2</color>，此版本由独立打包器进行构建，并未同整包进行完善验收，遇见BUG是正常情况，请提交issue反馈\n\n<color=#00C3FFFF>游玩提示</color>\n如果<color=#FF4040FF>深渊/剧情关卡/外传</color>出现<color=#FF4040FF>无法进入、持续加载或反复提示 fail</color>，尤其是在上一次对局异常退出后，请<color=#FF4040FF>彻底退出游戏、从后台划掉应用，再重新启动</color>。\n\n<color=#00C3FFFF>本次修复与改进</color>\n1. 修复部分圣痕打开详情时出现报错的问题。\n2. 修复新号引导要求进入尚未解锁的樱色轮回，导致无法继续操作的问题。\n3. 修复新手第二关无法正常进入，以及武器升级引导报错、卡住的问题。\n4. 修复新手补给引导漏发补给卡，以及抽卡后补给卡数量未及时刷新的问题。\n5. 修复武器解锁、装备出售、分解及作为强化材料使用时的相关问题；修复分解后装备仍留在列表、再次点击报错的问题。\n6. 修复樱火轮舞进入主线或深渊时卡在加载界面的问题。\n7. <color=#FF4040FF>兼容化</color>修复血色玫瑰释放大招时卡死的问题。\n8. 修复银狼的黎明进场、切换及释放大招时卡死的问题，并补齐相关召唤依赖。\n<color=#FF4040FF>9. 修复登录时需要反复点击才能进入游戏的问题。</color>\n10. 修复无助战好友问题。\n11. 修复商店购买角色碎片后数量未正确到账的问题；再次购买同种碎片时，补回旧版误存的碎片数量。\n12. 完善商店商品有效性与货架校验，避免无效商品上架或购买后错误发放。\n13. 修复轩辕篇 3-1、5-2、8-1 配置三支队伍后无法进入关卡的问题。\n\n<color=#00C3FFFF>问题反馈</color>\n如遇异常，请提交issue，并尽可能提供游戏包版本、手机型号、操作步骤、使用角色及报错截图；涉及存档的问题，请同时保留并上传出错时的存档，方便复现与排查，感谢。\n\n——来自 <color=#00C3FFFF>GITHUB/ClearwSea</color>\n鸣谢 Hssssssssi，以及各位AI。'

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
    announcements += [dict(
        id=201711 + show_type, type=show_type, weight=90,
        title_button="更新公告", title="", event_date_str="", content=UPDATE_CONTENT,
        banner_path="Server19/Announcement/Update", mark=0,
        begin_time=1767225600, end_time=2145916800, update_time=1794096000,
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
