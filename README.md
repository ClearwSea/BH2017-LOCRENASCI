[中文](README.md) · [English](README_ENG.md)

> 本 README 由 Agent 自动生成，内容请以实际情况为准。

# BH2017-LOCRENASCI

最新修复与验收范围见[更新日志](CHANGELOG.md)。

> 本项目主要采用 VIBECODING 方式开发。代码可能存在问题，敬请谅解；欢迎开发者阅读、验证和改进。

BH2017-LOCRENASCI 是面向 Android 1.9 客户端的本地运行与兼容适配源码项目。仓库提供本项目自行用 **Python 编写的本地服务端**、跨版本表单恢复、客户端补丁、资源处理代码及 Android 启动组件。

你可以直接研究和修改这些代码，将仓库交给 Agent 协作开发，或调用现有脚本与命令行生成所需数据和应用。配套 Windows 构建器为完整 APK 组装提供图形界面，也是其中一种使用方式。 Windows离线构建器可从[Releases](https://github.com/ClearwSea/BH2017-LOCRENASCI/releases)下载。

功能以 **2026年11月2日版本**为基础，不代表最新开发进度；需要后续功能的开发者可在此基础上自行扩展。

## 仓库目录

- `src/`：服务端、构建器、原生适配、规则和测试。
- `configs/`：构建配置示例。
- `docs/`：开发与使用文档。
- `launch_gui.py`：图形构建器入口；命令行仍使用 `python -m packager`。

## 选择使用方式

| 方式 | 从哪里开始 |
| --- | --- |
| 自行阅读、修改与扩展 | 阅读[源码与开发入口](docs/roadmap.md)，按模块修改服务端、规则、补丁或资源处理 |
| 与 Agent 协作开发 | 将仓库作为工作目录，提供目标和输入版本；入口见[开发约定](AGENTS.md)与[文档导航](docs/README.md) |
| 使用命令行和生成脚本 | 按需恢复表单、生成运行数据或组装APK，见[构建与输入](docs/build.md)与[打包器接口](src/packager/README.md) |
| 使用 Windows 图形构建器 | 选择客户端、资源与工具，生成APK和视频包，见[桌面构建器](docs/desktop-builder.md) |

## 准备材料与空间

阅读和修改源码可以直接开始。需要完整生成 Android 应用时，准备以下输入；单独开发某个模块时按该模块的数据依赖准备。

| 输入 | 用途 |
| --- | --- |
| 1.9 客户端 APK | 游戏包底、协议与原生库 |
| 2.4 参考客户端 APK | 提取表单及所需客户端资源，转换到1.9结构 |
| 7.x PC Windows 资源目录 | 提供语音与视频；选择直接包含`Audio/`和`Video/`的`StreamingAssets`目录 |
| 独立补充资源 ZIP | 提供7张配套图片与当前7.0资源缺少的5段旧CG |
| 兼容存档 | 另行提供，在应用安装后导入 |

客户端与7.x资源由使用者自行准备。[构建与输入](docs/build.md)介绍版本、目录和工具要求，[补充资源格式](assets/README.md)介绍ZIP结构。

### 客户端参考信息

本仓库不提供原始游戏客户端和完整游戏资源包。以下是维护者在公开互联网找到的第三方信息，仅供参考；内容、版本及可用性由原发布者提供，本项目不作保证。

| 参考内容 | 第三方信息 |
| --- | --- |
| V1.9 | [BV1UU4u6yE8R](https://www.bilibili.com/video/BV1UU4u6yE8R/) |
| V2.4演示版 | [BV1zJ411N7Qz](https://www.bilibili.com/video/BV1zJ411N7Qz/) |
| V7.0端 | [BV1xCpPezEeM](https://www.bilibili.com/video/BV1xCpPezEeM/) |

### 本地空间

**本地空间建议：**单轮完整构建为解压、转换、中间APK和成品额外预留 **20 GiB** 可用空间；保留多轮构建结果建议 **30 GiB以上**。客户端原包、7.x完整资源和工具包的体积另计；若全部放在同一磁盘，按“输入与工具的实际体积 + 20 GiB”规划。详见[空间预留](docs/build.md#本地空间)。

## 生成应用与运行

命令行或图形构建器可依次完成表单恢复、项目规则应用、兼容补丁、资源转换和APK组装。图形构建器输出`崩坏3·2017 独立版.apk`和同次生成的`client-videos.zip`；命令行的输出路径见[构建说明](docs/build.md)。

安装生成的APK，在启动界面导入配套视频包及兼容存档，再启动游戏。启动界面提供资源与存档管理，以及正常1×/辅助20×伤害选择。

覆盖更新沿用相同签名。使用图形构建器时，密钥路径留空会自动生成并复用本机密钥；填写及备份方式见[签名说明](docs/desktop-builder.md#签名)。游戏和Python运行时使用ARM32，设备要求见[Android兼容说明](docs/android-compatibility.md)。

### 已实测设备

以下设备由维护者实际运行测试，供参考；未列出的设备不保证相同表现。

| 设备 | 系统环境 | SoC | RAM |
| --- | --- | --- | --- |
| SONY SOV36 | Android 8.1 / Android 9（官方类原生） | Snapdragon 835 | 4 GB |
| Razer Phone 1 | Android 9（官方类原生） | Snapdragon 835 | 8 GB |
| Razer Phone 2 | Android 9（官方类原生） | Snapdragon 845 | 8 GB |
| OnePlus PJZ110 | Android 15（PJZ110_15.0.0.860(CN01)，系统自带Tango转译层） | Snapdragon 8 Elite | 16 GB |

## 源码导航

| 位置 | 内容 |
| --- | --- |
| 根目录`server19.py`及业务模块 | Python本地服务端、协议处理、业务逻辑与缓存 |
| `src/rules/`、`src/profiles/`与项目配置 | 业务规则、字段映射、输入参考与版本适配 |
| 根目录生成模块、`src/scripts/`、`src/tools/` | 表单恢复、客户端补丁、资源转换和组装工具 |
| `src/android-server-probe/` | Android启动界面、Python承载层与存档管理 |
| [`src/packager/`](src/packager/README.md) | 命令行、GUI与构建阶段调度 |
| [`docs/`](docs/README.md)、`src/tests/` | 使用与开发文档、隔离检查代码 |

[功能范围](docs/status.md)介绍组件职责，[源码与开发入口](docs/roadmap.md)介绍修改位置，[数据与规则来源](docs/data-sources.md)区分原表派生、兼容配置和项目规则。

## 素材与许可

游戏客户端、完整官方表单、原生库和音视频由外部输入提供。补充图片基于官方素材制作，5段CG引用自官方其他版本提取；它们作为独立补充资源包加载，不进入源码、构建器内建资源或CI，也不适用项目源码许可。兼容存档另行提供。

本项目自有源码采用[MIT许可证](LICENSE)，版权署名为ClearwSea。第三方依赖及外部素材的许可说明见[NOTICE](NOTICE.md)，各类配置和素材的来源见[数据与规则来源](docs/data-sources.md)。

## 致谢

感谢参与开发、研究、测试和反馈的开发者，以及 ChatGPT、DeepSeek、Claude、Gemini 在代码编写、分析与文档工作中的帮助。
