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


UPDATE_CONTENT = '<color=#FF4040FF>该公告面向V0.1.2</color>，此版本由独立打包器进行构建，并未同整包进行完善验收，遇见BUG是正常情况，请提交issue反馈\n\n<color=#00C3FFFF>游玩提示</color>\n如果<color=#FF4040FF>深渊/剧情关卡/外传</color>出现<color=#FF4040FF>无法进入、持续加载或反复提示 fail</color>，尤其是在上一次对局异常退出后，请<color=#FF4040FF>彻底退出游戏、从后台划掉应用，再重新启动</color>。\n\n<color=#00C3FFFF>本次修复与改进</color>\n1. 修复部分圣痕打开详情时出现报错的问题。\n2. 修复新号引导要求进入尚未解锁的樱色轮回，导致无法继续操作的问题。\n3. 修复新手第二关无法正常进入，以及武器升级引导报错、卡住的问题。\n4. 修复新手补给引导漏发补给卡，以及抽卡后补给卡数量未及时刷新的问题。\n5. 修复武器解锁、装备出售、分解及作为强化材料使用时的相关问题；修复分解后装备仍留在列表、再次点击报错的问题。\n6. 修复樱火轮舞进入主线或深渊时卡在加载界面的问题。\n7. <color=#FF4040FF>兼容化</color>修复血色玫瑰释放大招时卡死的问题。\n8. 修复银狼的黎明进场、切换及释放大招时卡死的问题，并补齐相关召唤依赖。\n<color=#FF4040FF>9. 修复登录时需要反复点击才能进入游戏的问题。</color>\n10. 修复无助战好友问题。\n11. 修复商店购买角色碎片后数量未正确到账的问题；再次购买同种碎片时，补回旧版误存的碎片数量。\n12. 完善商店商品有效性与货架校验，避免无效商品上架或购买后错误发放。\n13. 修复轩辕篇 3-1、5-2、8-1 配置三支队伍后无法进入关卡的问题。\n\n<color=#00C3FFFF>问题反馈</color>\n如遇异常，请提交issue，并尽可能提供游戏包版本、手机型号、操作步骤、使用角色及报错截图；涉及存档的问题，请同时保留并上传出错时的存档，方便复现与排查，感谢。\n\n——来自 <color=#00C3FFFF>GITHUB/ClearwSea</color>\n鸣谢 Hssssssssi，以及各位AI。'

UPDATE_CONTENT_V013 = '<color=#FF4040FF>该公告面向V0.1.3</color>，此版本由独立打包器进行构建，并未同整包进行完善验收，遇见BUG是正常情况，请提交issue反馈\n\n<color=#00C3FFFF>游玩提示</color>\n如果<color=#FF4040FF>深渊/剧情关卡/外传</color>出现<color=#FF4040FF>无法进入、持续加载或反复提示 fail</color>，尤其是在上一次对局异常退出后，请<color=#FF4040FF>彻底退出游戏、从后台划掉应用，再重新启动</color>。\n<color=#00C3FFFF>本次修复与改进</color>\n1. 修复使用角色碎片解锁女武神时出现报错、无法解锁的问题。\n2. 修复指挥官达到9级后，女武神·战车未自动解锁的问题\n3. 修复战场疾风教学关黑屏、报错的问题。\n4. 补齐布洛妮娅相关教学关脚本，修复教学关依赖问题\n5. 修复角色在进出关卡、结算切换场景时面部模型变黑的问题。\n6. 修复新手1-6编队引导过程中出现报错的问题。\n7. 为方便购买，角色碎片商品调整为<b>每次购买20片</b>\n8. 活动公告、游戏公告新增按版本区分的更新公告，保留历史版本内容。\n9. 修改部分启动前页面的公告信息\n10. 修复新账号引导流程的错乱以及首次登录状态失效的问题\n11. 兼容修复部分女武神推荐装备数据异常，导致角色详情报错、技能及换装页面无法正常使用的问题。\n12. 修复登录时剧情章节数据尚未初始化，导致进入舰桥出现报错的问题。\n\n<color=#00C3FFFF>问题反馈</color>\n如遇异常，请提交issue，并尽可能提供游戏包版本、手机型号、操作步骤、使用角色及报错截图；涉及存档的问题，请同时保留并上传出错时的存档，方便复现与排查，感谢。\n\n——来自 <color=#00C3FFFF>GITHUB/ClearwSea</color>\n鸣谢 Hssssssssi，以及各位AI。'

UPDATE_CONTENT_V014 = '<color=#FF4040FF>该公告面向V0.1.4</color>，此版本由独立打包器进行构建，并未同整包进行完善验收，遇见BUG是正常情况，请提交issue反馈\n\n<color=#00C3FFFF>本次修复与改进</color>\n1. 开放主线第1—6章困难与噩梦关卡，<b>未做完全测试</b>。\n2. 修复困难难度介绍引导无法正常继续的问题。\n<color=#FF4040FF>3. 修复深渊主动退出后，更换角色或调整队伍顺序再次挑战时提示 fail 的问题。</color>\n4. 修复装备穿戴成功后页面未及时刷新，再次点击出现异常提示的问题。\n5. <color=#FF4040FF>兼容恢复</color>女武神战斗力显示。\n6. 修复影舞冲击背刺技能无法正常升级的问题。\n7. 修复部分大剑主动技能动作及触发异常，补齐相关能力依赖。\n8. <color=#FF4040FF>兼容修复</color>仿灵刀·冰昙天、11th圣遗物等部分武器导致的进场或战斗异常。\n9. 修复独眼巨人初型三层蓄力攻击后卡死的问题。\n10. <color=#FF4040FF>兼容修复</color>轩辕剑连招异常的问题。\n11. 补齐部分装备技能信息，修复相关详情页面报错的问题。\n12. 修复精准与扩充补给中，200抽 UP 保底可能无法正常触发的问题。\n\n<color=#00C3FFFF>问题反馈</color>\n如遇异常，请提交issue，并尽可能提供游戏包版本、手机型号、操作步骤、使用角色及报错截图；涉及存档的问题，请同时保留并上传出错时的存档，方便复现与排查，感谢。\n\n——来自 <color=#00C3FFFF>GITHUB/ClearwSea</color>\n鸣谢 Hssssssssi，以及各位AI。'

UPDATE_CONTENT_V015 = '<color=#FF4040FF>该公告面向V0.1.5</color>，此版本由独立打包器进行构建，并未同整包进行完善验收，遇见BUG是正常情况，请提交issue反馈\n\n<color=#00C3FFFF>本次修复与改进</color>\n1. <color=#FF4040FF>兼容修复</color>八重樱封印罐子无法正常开启/出售的问题。\n2. 修复宝藏、体力药水无法使用/出售的问题。\n<color=#FF4040FF>3.修复舰长升至20级时，降临活动解锁引导卡住、\n活动入口消失及关卡列表为空的问题。</color>\n4. <color=#FF4040FF>兼容开放</color>崩坏降临活动关，<color=#FF4040FF>未做完全测试</color>。\n5. <color=#FF4040FF>兼容修复</color>崩坏降临活动关卡掉落异常的问题。\n6. 降临活动兼容规则：\n\u3000\u30001. 兼容调整为<b>每周开放两个、四周循环</b>，每周一循环更换。\n\u3000\u30002. <b>每个活动每日可成功通关3次</b>。\n\u3000\u30003.失败或退出不扣成功次数，开战仍正常消耗体力；\n\u3000\u3000活动换期前已开始的战斗可正常结算。\n\n<color=#00C3FFFF>问题反馈</color>\n如遇异常，请提交issue，并尽可能提供游戏包版本、手机型号、操作步骤、使用角色及报错截图；涉及存档的问题，请同时保留并上传出错时的存档，方便复现与排查，感谢。\n\n——来自 <color=#00C3FFFF>GITHUB/ClearwSea</color>\n鸣谢 Hssssssssi，以及各位AI。'

UPDATE_CONTENT_V016 = '<color=#FF4040FF>该公告面向V0.1.6</color>，此版本由独立打包器进行构建，并未同整包进行完善验收，遇见BUG是正常情况，请提交issue反馈\n\n<color=#00C3FFFF>本次修复与改进</color>\n1. 修复雷天使等装备强化、进化报错，以及部分降临武器进化配方和同名装备素材消耗异常的问题。\n2. 修复金币道具错误提示仓库上限，以及装备强化、进化、技能升级和补给后任务进度未及时刷新的问题。\n3. <color=#FF4040FF>兼容修复</color>薛定谔（上）等部分圣痕技能配置导致的关卡加载异常；修复女武神·强袭「连段保持」、真炎幸魂「梦稽古」无法解锁的问题。\n<color=#FF4040FF>4. 修复轩辕篇、蚩尤篇、永世回忆领奖后红点残留、一键领取故障问题；</color>\n5. 修复部分成就领奖报错和空白奖励弹窗。\n6. 修复商店部分材料、活动礼盒详情打开异常及图片缺失的问题。\n7. 修复武器、圣痕及材料图鉴中的图片错误、串图和碎片图标显示异常；<color=#FF4040FF>暂无资源的条目使用文字占位显示</color>。\n8. 修复「糖果恶魔」服装图片；紫苑无名换色服装兼容命名为「处刑装·红苑」，使用默认服装图片。\n9. 开放所有46套服装的列表显示，可配合存档编辑器V0.8.2调整解锁。\n\n<color=#00C3FFFF>问题反馈</color>\n如遇异常，请提交issue，并尽可能提供游戏包版本、手机型号、操作步骤、使用角色及报错截图；涉及存档的问题，请同时保留并上传出错时的存档，方便复现与排查，感谢。\n\n——来自 <color=#00C3FFFF>GITHUB/ClearwSea</color>\n鸣谢 Hssssssssi，以及各位AI。'

UPDATE_CONTENT_V017 = '<color=#FF4040FF>当前版本为V0.1.7</color>，此版本由独立打包器进行构建，并未同整包进行完善验收，遇见BUG是正常情况，请提交issue反馈\n\n<color=#00C3FFFF>本次修复与改进</color>\n1. 修复女武神达到当前等级上限、经验条已满后，提升舰长等级仍无法继续使用经验芯片升级的问题。\n2. 修复崩坏碎片等部分物品点击「获取」时出现报错，并导致后续界面显示异常的问题。\n3. 按本地实际商店、关卡掉落及任务奖励修正物品获取列表，修正商店名称并合并重复途径；移除当前不存在或不产出该物品的入口，没有有效途径的物品不再显示「获取」按钮。\n4. 构建器改为<b>基础包＋构建主包</b>分开提供。首次使用需准备基础包和主包；后续工具链未变更时，只需下载新版主包并导入构建器，补充资源包继续独立提供。\n\n<color=#00C3FFFF>问题反馈</color>\n如遇异常，请提交issue，并尽可能提供游戏包版本、手机型号、操作步骤、使用角色及报错截图；涉及存档的问题，请同时保留并上传出错时的存档，方便复现与排查，感谢。\n\n——来自 <color=#00C3FFFF>GITHUB/ClearwSea</color>\n鸣谢 Hssssssssi，以及各位AI。'


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
        id=201711 + show_type, type=show_type, weight=80,
        title_button="更新公告V0.1.2", title="", event_date_str="", content=UPDATE_CONTENT,
        banner_path="Server19/Announcement/Update", mark=0,
        begin_time=1767225600, end_time=2145916800, update_time=1794096000,
    ) for show_type in (0, 1)]
    announcements += [dict(
        id=201721 + show_type, type=show_type, weight=90,
        title_button="更新公告V0.1.3", title="", event_date_str="", content=UPDATE_CONTENT_V013,
        banner_path="Server19/Announcement/Update", mark=0,
        begin_time=1767225600, end_time=2145916800, update_time=1794096000,
    ) for show_type in (0, 1)]
    announcements += [dict(
        id=201731 + show_type, type=show_type, weight=95,
        title_button="更新公告V0.1.4", title="", event_date_str="", content=UPDATE_CONTENT_V014,
        banner_path="Server19/Announcement/Update", mark=0,
        begin_time=1767225600, end_time=2145916800, update_time=1794240000,
    ) for show_type in (0, 1)]
    announcements += [dict(
        id=201741 + show_type, type=show_type, weight=98,
        title_button="更新公告V0.1.5", title="", event_date_str="", content=UPDATE_CONTENT_V015,
        banner_path="Server19/Announcement/Update", mark=0,
        begin_time=1767225600, end_time=2145916800, update_time=1794326400,
    ) for show_type in (0, 1)]
    announcements += [dict(
        id=201751 + show_type, type=show_type, weight=99,
        title_button="更新公告V0.1.6", title="", event_date_str="", content=UPDATE_CONTENT_V016,
        banner_path="Server19/Announcement/Update", mark=0,
        begin_time=1767225600, end_time=2145916800, update_time=1794412800,
    ) for show_type in (0, 1)]
    announcements += [dict(
        id=201761 + show_type, type=show_type, weight=101,
        title_button="更新公告V0.1.7", title="", event_date_str="", content=UPDATE_CONTENT_V017,
        banner_path="Server19/Announcement/Update", mark=0,
        begin_time=1767225600, end_time=2145916800, update_time=1794412801,
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
