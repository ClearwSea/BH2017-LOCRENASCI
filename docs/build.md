# 构建与输入

仓库中的服务端、补丁和生成模块可用于自行开发，统一命令行可按阶段生成数据或应用；Windows用户也可选择[图形构建器](desktop-builder.md)。本页介绍输入、空间要求和现有构建入口。

## 输入版本与目录

| 配置项 | 选择内容 |
| --- | --- |
| `client19` | 1.9客户端APK |
| `client24` | 2.4参考客户端APK |
| `resources7x` | PC Windows版的`StreamingAssets`目录，直接包含`Audio/`与`Video/` |
| `supplements` | 独立补充资源ZIP；命令行也支持解压目录 |

```text
inputs/
  client-1.9.apk
  client-2.4.apk
  resources-7x/StreamingAssets/
    Audio/GeneratedSoundBanks/Windows/
    Video/
  supplements.zip
```

1.9/2.4参考配置见[`src/profiles/android-launcher-20261102.json`](../src/profiles/android-launcher-20261102.json)，参考哈希见[`src/profiles/input-references.json`](../src/profiles/input-references.json)。整体APK哈希或大小不同仍可尝试构建；原生补丁需要匹配所适配的内部库。7.x相近版本可按所需音视频的实际覆盖使用。

补充ZIP提供7张配套图片与当前7.0集合缺少的5段旧CG，目录格式见[补充资源说明](../assets/README.md)。图片和CG由外部资源包加载，不随源码或构建器内置。兼容存档在APK安装后导入。

## 本地空间

单轮完整构建建议为输出与缓存额外预留 **20 GiB** 可用空间；同时保留多轮工作目录和成品时，建议 **30 GiB以上**。这些空间用于资源解压、音视频转换、中间APK和最终产物。

原始客户端、7.x完整资源目录和离线工具包另计。输入、工具与输出全部位于同一磁盘时，按“输入与工具的实际体积 + 20 GiB”估算；实际用量随资源组合、缓存和保留轮数变化。仅读取或修改源码时，无需预留完整构建空间。

## 从源码使用

可直接修改src/ 中的服务端模块、`src/rules/`配置及生成工具；与Agent协作时，先提供仓库、开发目标和输入版本，阅读入口见[源码与开发入口](roadmap.md)。服务端运行和客户端适配仍需要相应的生成数据与资源。

下面的命令行支持完整APK和独立表单阶段。希望使用图形界面时，也可以从源码启动GUI。

## 从源码启动GUI

程序目录布局如下；`app/`中放置仓库源码，同级`tools/`中放置配套离线工具包：

```text
builder/
  app/
    launch_gui.py
    packager/  # 命令行兼容入口
    src/       # 实现代码与构建资源
    ...
  tools/
    python/python.exe
    android/
    ...
```

在`builder/`目录运行：

```console
./tools/python/python.exe -B -s app/launch_gui.py .
```

GUI操作、四项签名填写及输出位置见[桌面构建器](desktop-builder.md)。窗口程序入口源码位于仓库的`src/tools/DesktopLauncher.cs`。

## 命令行生成APK

在仓库根目录准备`src/requirements-build.txt`所列依赖及Android工具链、Zig、FFmpeg和vgmstream。具体目录与版本见[打包器说明](../src/packager/README.md#构建环境)。

复制`configs/packager-original.example.json`，填写输入、工具、独立工作目录及签名配置，通过环境变量`BH3_KEYSTORE_PASSWORD`和`BH3_KEY_PASSWORD`提供签名密码，然后运行：

```console
python -B -m packager build --target apk --config configs/packager-original.example.json
```

命令行输出在所配`work_dir`中：

```text
candidate.apk
embedded/client-videos.zip
original-build.json
logs/
```

桌面GUI会将成品移至按时间命名的输出目录，命名为`崩坏3·2017 独立版.apk`和`client-videos.zip`。两种入口使用同一套原始输入构建流程。

## 安装与导入

安装APK，在启动界面导入同次构建的视频ZIP和兼容存档，再点击开始游戏。主资源及本地服务端已集成到APK中。

覆盖更新沿用原签名；换签名前先导出存档。启动界面支持资源/存档重选、备份和导出，以及正常1×/辅助20×伤害选择。伤害设置重开应用后生效。ARM32设备要求见[Android兼容说明](android-compatibility.md)。

## 单独生成表单

复制`configs/packager.example.json`并填写客户端输入。以下两条命令分别使用新的工作目录：

```console
python -B -m packager build --target data --config configs/packager.example.json
python -B -m packager build --target tables --config configs/packager.example.json
```

`data`输出协议、251张基础表和材料导航；`tables`继续应用角色/材料补行、商店、每日使命、外传入口等规则，生成251张有效服务端表。完整APK阶段继续生成派生目录、客户端数据和资源。

六关经验/金币比例由`stage_ratios`选择：默认`baseline`沿用该版本比例，`repaired`采用导出器中的比例修复。参数与继续构建方法见[打包器接口](../src/packager/README.md)。
