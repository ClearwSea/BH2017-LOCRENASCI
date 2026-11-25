# 迅羽 601 实验基线交接 / Fu Hua 601 experimental handoff

2026-11-24，Asia/Shanghai。[实验基线清单](../../../FUKA601-EXPERIMENTAL-BASELINE.json) · [完整调查与验收记录](../../work/agent-handoff/fuka601.md)

## 接手基线

使用 `BH2017-V0.2.1-fuka601-b3-avatar-icon.apk`（Part A），SHA-256 `edb7ab7520fc3d39275fdd47d7838d0fe7cfc473b8f52e82cf376c6fce2224c9`。它以 `battle-lab-r9` 开始的 601 实验链为父链，包含 B2 的战斗 HUD 图标和新版底栏头像，中央预览使用 1.9 原生模型。#24/#25 仍以各自验收检查点为准，本基线不代表两项修复已合并发布。

- **选人已验收**。SOV36 Android 9 与雷蛇 1 Android 8.1 通过 Part A 选人，两台设备在试验后均回退到同一哈希。中央的 1.9 早期模型仍有此前确认的外观差异。
- **战斗证据范围**。SOV36 的 B1/B2 前序包验证了训练关 `10998` 的 601 普攻 A1–A6、闪避回待机和 HUD 图标。Part A 与 B2 的功能差异只有选人头像所需的两个资产和资源索引。Part A 有训练关入场截图，Part A 专属完整命中回归缺有效日志，见调查 §20–21.3。
- **实验档与拳套**。`sov36-fuka601-fixture.json` 已配迅羽 601、A 级 40 级、1 级 `20611`。当前用 1.9 测试拳套作为战斗入场兼容资源。正式资源、强化进化和普通获得途径均需单独验收。

## 暂挂项

中央 2.0 选人模型维持 **OPEN / 暂挂**。直接换模型的 Part B 选中 601 时曾在 SOV36 触发应用内 `SIGSEGV`。改用 1.9 原生动画的 `anim19` 能切人，SOV36 和雷蛇 1 都只显示粉白的脸。两台系统均保持运行。已做的静态核查涵盖序列化、待机采样和蒙皮包围盒。恢复此任务时需补同帧 Body 与 Face 的渲染状态和绘制提交证据，见调查 §25–34。

## 后续优先级

1. **玩法**。按 1.9 原生接口先梳理迅羽分支、各技能表和 `SKL02` 点按、长按、松手，再处理必杀、SP 扣除和退出条件。遇到原生缺失时记录 `OPEN` 和具体原因，由用户评审兼容方案后实施。训练关验收覆盖切人复位、回待机、伤害结算和保存。
2. **武器和装备**。先核 `20611–20613` 的类型与进化链、正式拳套模型／图标／挂点、装备和切换、强化进化与消耗。再核迅羽相关圣痕或同期装备的效果、装备限制及获取渠道。优先沿用原生客户端和现有服务端表，使用隔离档验证。
3. **集成**。玩法和装备可验收后再决定是否接入普通获取。旧中央模型可继续作为实验包的可用预览。模型调查保留独立证据，验收派单和正式发布另行审批。

## 构建与恢复入口

- 实验构建脚本与原回执位于 `release-v0.2.1/work/fuka601-a1-validation/`。`receipt-b3-avatar-icon.json` 记录 B2 父包及 2.0 头像来源。当前工作目录没有早期交接提到的独立 `build_fuka_b3_avatar_icon.py`，恢复依靠已验证的原签名 APK 增量。完整打包器的重新接入是后续集成事项。
- 冷库检查点复用正式 v0.2.1 的验收 APK 和 `client-videos.zip`。按清单指向的 `RESTORE.md` 恢复到新文件，校验 SHA-256 后在隔离设备使用。保留旧存档时使用覆盖安装，首次启动用启动页选择视频资源和 601 隔离档。

## English summary

Part A is the local experimental checkpoint. It keeps the stock 1.9 center preview and uses the newer roster portrait. The roster was verified on SOV36 and Razer Phone. Earlier B1/B2 builds provide the combat evidence. Full hit-trace regression on Part A remains pending. The 2.0 center preview is paused. Next priorities are move sets, skills, ultimate and SP behavior, then fists, equipment, progression and acquisition. Keep restoration and device tests isolated from public releases and player saves.
