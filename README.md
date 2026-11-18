<div align="center">
  <img src="docs/assets/logo.png" alt="BH2017-LOC-RENASCI Logo" width="164"><br>
  <h1>BH2017-LOC-RENASCI</h1>
  <p>面向崩坏BH3_CN Android V1.9 客户端的本地兼容运行方案，提供 Python 自写本地服务端、跨版本表单恢复、客户端原生补丁与离线构建工具。</p>

简体中文 | [English](README_ENG.md)

  <p>
    <img src="https://img.shields.io/badge/platform-Android%20ARM32-007ec6" alt="Platform">
    <img src="https://img.shields.io/badge/runtime-Python-3776ab" alt="Runtime">
    <a href="https://github.com/ClearwSea/BH2017-LOCRENASCI/releases"><img src="https://img.shields.io/github/v/release/ClearwSea/BH2017-LOCRENASCI" alt="Latest Release"></a>
    <a href="https://github.com/ClearwSea/BH2017-LOCRENASCI/releases"><img src="https://img.shields.io/github/downloads/ClearwSea/BH2017-LOCRENASCI/total" alt="Total Downloads"></a>
    <a href="LICENSE"><img src="https://img.shields.io/github/license/ClearwSea/BH2017-LOCRENASCI" alt="License"></a>
  </p>

  <p>
    <a href="https://github.com/ClearwSea/BH2017-LOCRENASCI/releases">📥 下载最新版</a> ·
    <a href="#-选择使用方式">🚀 快速上手</a> ·
    <a href="#-windows-构建器首次使用与更新">🧱 Windows 构建器</a> ·
    <a href="#-详细参考源码导航与实测列表">📖 文档与源码</a> ·
    <a href="docs/agent-guide.md">🤖 Agent 协作</a> ·
    <a href="https://github.com/ClearwSea/BH2017-LOCRENASCI">⭐ 点亮小星星</a>
  </p>
</div>

---

## BH2017-LOC-RENASCI 是什么

**BH2017-LOCRENASCI** 是面向 Android 1.9 客户端的本地运行与兼容适配源码项目。仓库提供本项目自行用 **Python 编写的本地服务端**、跨版本表单恢复、客户端补丁、资源处理代码及 Android 启动组件。

你可以直接研究和修改这些代码，将仓库交给 Agent 协作开发，或调用现有脚本与命令行生成所需数据和应用；配套 Windows 离线构建器提供图形界面，以**基础包＋构建主包**分开提供，可从 [Releases](https://github.com/ClearwSea/BH2017-LOCRENASCI/releases) 下载。最新修复与验收范围见 [更新日志](CHANGELOG.md)。

> [!NOTE]
> - 本项目主要采用 **VIBECODING** 方式开发。代码可能存在问题，敬请谅解；欢迎开发者阅读、验证和改进。
> - 仓库内项目不代表最新开发进度；开发者可在此基础上自行扩展与分支。
> - **AI / LLM / Agent 入口**：如果你是 AI/LLM/Agent，请先阅读 [Agent 使用说明：构建与游玩](docs/agent-guide.md)（[English](docs/agent-guide.en.md)），按基础包与构建主包分离的流程协助用户准备材料、构建、安装和游玩。

## ✨ 核心能力

- **Python 本地服务端**：自研本地协议处理、业务逻辑、缓存与本地数据控制（`src/server19.py` 及业务模块）。
- **跨版本表单与资源适配**：基于 2.4 参考客户端恢复表单并转换至 1.9 结构，将 7.x PC 端语音与视频转换为手机端可用格式。
- **Android 启动页与内置工具**：提供启动界面、ARM32 Python 承载层、存档管理/历史备份导出、正常 1× / 辅助 20× 伤害选择，以及记忆战场下期 Boss 与深渊温度的本地服务端调整。
- **双模式构建器**：支持 Windows 图形界面（`launch_gui.py` / `构建器.exe`）与命令行（`python -m packager`），依次完成表单恢复、项目规则应用、兼容补丁、资源转换与 APK 组装。
- **基础包 + 主包分离更新**：基础包保存离线工具链与导入入口，工具链未变更时后续只需导入新版主包 ZIP，支持文件完整性与兼容性检查及「恢复上一版」。

## ⚠️ 重要说明与前提边界

> [!CAUTION]
> **素材与许可边界**
>
> 本仓库**不提供**原始游戏客户端和完整游戏资源包。游戏客户端、完整官方表单、原生库和音视频由外部输入提供。补充图片基于官方素材制作，5 段 CG 引用自官方其他版本提取；它们作为独立补充资源包加载，不进入源码、构建器内建资源或 CI，也不适用项目源码许可。

> [!WARNING]
> **存档与签名密钥保留提示**
>
> - **替换存档不自动备份**：启动页更换存档会在启动游戏时直接导入，不再确认，也不自动备份旧档；需要保留进度时请务必**先导出**。
> - **保留签名密钥**：覆盖更新沿用相同签名。签名密钥、路径设置和日志保存在 `user-data/`，切换主包时保留这些数据；从旧版整包迁移时请保留原 `user-data/`（尤其是 `user-data/keys` 中的原签名密钥）。

> [!TIP]
> **本地磁盘空间规划**
>
> 单轮完整构建请为解压、转换、中间 APK 和成品额外预留 **20 GiB** 可用空间；保留多轮构建结果建议 **30 GiB 以上**。客户端原包、7.x 完整资源和工具包的体积另计；若全部放在同一磁盘，请按「输入与工具的实际体积 + 20 GiB」规划。详见 [空间预留](docs/build.md#本地空间)。

## 🚀 选择使用方式

| 方式 | 从哪里开始 |
| --- | --- |
| **使用 Windows 图形构建器（推荐）** | 先导入构建主包，再选择客户端、资源与工具，生成 APK 和视频包，见 [桌面构建器](docs/desktop-builder.md) |
| **使用命令行和生成脚本** | 按需恢复表单、生成运行数据或组装 APK（`python -m packager`），见 [构建与输入](docs/build.md) 与 [打包器接口](src/packager/README.md) |
| **自行阅读、修改与扩展源码** | 阅读 [源码与开发入口](docs/roadmap.md)，按模块修改服务端、规则、补丁或资源处理 |
| **与 Agent 协作开发** | 将仓库作为工作目录，提供目标和输入版本；入口见 [开发约定](AGENTS.md) 与 [文档导航](docs/README.md) |

## 🧱 Windows 构建器：首次使用与更新

构建器分包、补充资源与生成的游戏文件各有用途：

| 文件 | 用途 | 更新方式 |
| --- | --- | --- |
| `BH2017-LOCRENASCI-Builder-Base-Windows-x64.zip` | **基础包**：导入入口、Python、Android 工具链、音视频工具及配套第三方资料 | 首次下载；工具链或基础入口变化时按 Release 更新 |
| `BH2017-LOCRENASCI-Builder-Main-v<版本>.zip` | **主包**：当前版本完整项目程序、构建界面、服务端、规则和补丁源码 | 下载所需版本并通过基础包导入，可跨主包版本更新 |
| `BH2017-LOCRENASCI-Supplements-v<版本>.zip` | **补充资源**：构建前使用的补充图片和旧 CG | 按 Release 指定版本选择；可复用兼容旧包（格式见 [补充资源格式](assets/README.md)） |
| `client-videos.zip` | **手机视频包**：构建后生成 | 与生成的 APK 配套，在手机启动页选择 |

- **首次使用**：将基础包解压到 C 盘较短的路径（如 `C:\BH3Builder`，路径过深可能导致 Android 工具无法启动）→ 运行 `构建器.exe` → 点击「导入构建主包」选择主包 ZIP（无需手动覆盖程序目录）→ 点击「打开构建界面」→ 选择输入材料并构建。
- **后续更新与回退**：保留基础包，导入新版主包。构建器会检查文件完整性和工具链兼容性；提示不匹配时，按该版 Release 更新基础包。可通过「恢复上一版」切回前一主包。签名密钥、路径设置和日志保存在 `user-data/`，主包切换保留这些数据。
- **从旧版整包迁移（例如 V0.1.6）**：先准备新基础包，保留原 `user-data/`，将其复制到新基础包根目录，核对工具和输出路径后导入主包。尤其要保留 `user-data/keys` 中的原签名密钥。

## 📦 准备材料与生成运行

阅读和修改源码可以直接开始。需要完整生成 Android 应用时，准备以下输入；单独开发某个模块时按该模块的数据依赖准备：

| 输入 | 用途 |
| --- | --- |
| **1.9 客户端 APK** | 游戏包底、协议与原生库 |
| **2.4 参考客户端 APK** | 提取表单及所需客户端资源，转换到 1.9 结构 |
| **7.x PC Windows 资源目录** | 提供语音与视频；选择直接包含 `Audio/` 和 `Video/` 的 `StreamingAssets` 目录 |
| **独立补充资源 ZIP** | 提供配套图片和需要补充的旧 CG，内容以所选 Release 及 [资源格式说明](assets/README.md) 为准 |
| **兼容存档** | 安装后可导入已有存档，也可在启动页的内置编辑器中创建 |

客户端与 7.x 资源由使用者自行准备，[构建与输入](docs/build.md) 介绍版本、目录和工具要求。

**应用生成与运行**：图形构建器输出 `崩坏3·2017 独立版.apk` 和同次生成的 `client-videos.zip`（命令行的输出路径见 [构建说明](docs/build.md)）。安装生成的 APK，在启动页选择同次构建的视频包，并导入兼容存档或使用内置编辑器创建存档，再启动游戏。使用图形构建器时，密钥路径留空会自动生成并复用本机密钥（填写及备份方式见 [签名说明](docs/desktop-builder.md#签名)）。游戏和 Python 运行时使用 **ARM32**，设备要求见 [Android 兼容说明](docs/android-compatibility.md)。

## 📚 详细参考、源码导航与实测列表

<details>
<summary>🧭 源码目录导航（点击展开）</summary>

| 位置 | 内容 |
| --- | --- |
| `src/server19.py` 及业务模块 | Python 本地服务端、协议处理、业务逻辑与缓存 |
| `src/rules/`、`src/profiles/` 与项目配置 | 业务规则、字段映射、输入参考与版本适配 |
| `src/` 中的生成模块、`src/scripts/`、`src/tools/` | 表单恢复、客户端补丁、资源转换和组装工具 |
| `src/android-server-probe/` | Android 启动界面、Python 承载层与存档管理 |
| [`src/packager/`](src/packager/README.md) | 命令行、GUI 与构建阶段调度（根目录 `launch_gui.py` 为图形构建器入口） |
| `configs/` | 构建配置示例 |
| [`docs/`](docs/README.md)、`src/tests/` | 使用与开发文档、隔离检查代码 |

延伸阅读：[功能范围](docs/status.md) · [源码与开发入口](docs/roadmap.md) · [数据与规则来源](docs/data-sources.md)

</details>

<details>
<summary>📱 已实测设备列表（5 款实测参考，点击展开）</summary>

以下设备由维护者实际运行测试，供参考；未列出的设备不保证相同表现。

| 设备 | 系统环境 | SoC | RAM |
| --- | --- | --- | --- |
| SONY SOV36 | Android 8.1 / Android 9（官方类原生） | Snapdragon 835 | 4 GB |
| Razer Phone 1 | Android 9（官方类原生） | Snapdragon 835 | 8 GB |
| Razer Phone 2 | Android 9（官方类原生） | Snapdragon 845 | 8 GB |
| OPPO PDRM00 | Android 12 | Snapdragon 865 | 8 GB |
| OnePlus PJZ110 | Android 15（`PJZ110_15.0.0.860(CN01)`，系统自带 Tango 转译层） | Snapdragon 8 Elite | 16 GB |

</details>

<details>
<summary>🔎 客户端参考信息（第三方信息，点击展开）</summary>

本仓库不提供原始游戏客户端和完整游戏资源包。以下是维护者在公开互联网找到的第三方信息，仅供参考；内容、版本及可用性由原发布者提供，本项目不作保证。

| 参考内容 | 第三方信息 |
| --- | --- |
| V1.9 | [BV1UU4u6yE8R](https://www.bilibili.com/video/BV1UU4u6yE8R/) |
| V2.4 演示版 | [BV1zJ411N7Qz](https://www.bilibili.com/video/BV1zJ411N7Qz/) |
| V7.0 端 | [BV1xCpPezEeM](https://www.bilibili.com/video/BV1xCpPezEeM/) |

</details>

## 🔗 关联项目

- **[BH-LOCRENASCI-ACT-EDIT](https://github.com/ClearwSea/BH-LOCRENASCI-ACT-EDIT)**：配套的 BH3 V1.9 离线存档修改器（Python / Tkinter，支持 Windows 单文件 EXE），可与启动页存档导入/导出配合使用。

## ❤️ 许可与致谢

本项目自有源码采用 [MIT 许可证](LICENSE)，版权署名为 **ClearwSea**。第三方依赖及外部素材的许可说明见 [NOTICE](NOTICE.md)，各类配置和素材的来源见 [数据与规则来源](docs/data-sources.md)。

感谢参与开发、研究、测试和反馈的开发者，以及 ChatGPT、DeepSeek、Claude、Gemini 在代码编写、分析与文档工作中的帮助。
