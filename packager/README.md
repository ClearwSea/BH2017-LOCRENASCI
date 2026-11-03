# 打包器

打包器读取1.9 APK、2.4参考APK、7.x PC Windows资源与独立补充ZIP，生成表单、服务端运行数据、原生兼容库、Android承载层、最终APK与配套视频包。

## 桌面入口

Windows GUI与配套离线工具包的布局、签名及输出说明见[桌面构建器](../docs/desktop-builder.md)。GUI仅执行本地构建，不下载依赖。

## 完整构建

复制 `packager-original.example.json` 并填写输入、工具和签名配置：

```console
python -B -m packager build --target apk --config packager-original.example.json
```

`resources7x` 指向包含 `Audio/` 与 `Video/` 的PC Windows版StreamingAssets目录；语音使用 `Audio/GeneratedSoundBanks/Windows/`。`profiles/android-launcher-20261102.json`列出参考输入。整个APK的参考哈希或大小不同仍可尝试构建；原生库、类型及资源结构按对应版本配置处理。

构建依次完成协议提取、251表恢复、项目规则、派生目录、原生差分补丁、客户端资源修补、7.x语音/视频转换、运行包配置、Android编译、APK组装、对齐和签名。原生补丁检查原库指纹及指令前像，输出需匹配该补丁配置。

输出位于配置的 `work_dir`：

```text
candidate.apk                    游戏与Python服务端的单APK
embedded/client-videos.zip        首次运行选择的配套外置包
original-build.json              构建阶段与实际补充输入
logs/                           编译及转换日志
```

`supplements`指定外部补充资源ZIP或目录，其中`images/`包含补给图、公告、舰桥横幅和图标，`videos/`包含缺失旧CG。格式与来源见[补充资源说明](../assets/README.md)。

## 补充视频

不同资源版本可能缺少旧CG。当前使用的7.0资源缺少以下5个文件，打包时通过外部补充资源包的`videos/`目录显式提供：

- `ExtraStory_BlackXuanyuan_01.mp4`
- `ExtraStory_BlackXuanyuan_02.mp4`
- `ExtraStory_BlackXuanyuan_03.mp4`
- `Sakura_4_CG12_SP_mux.mp4`
- `Season_CG01_Final_mux.mp4`

这些文件属于额外游戏资源，不随源码存放。构建清单分别记录USM转换与直接提供的视频。若自己的资源集合已包含所需视频，则直接转换；缺失或来源匹配不唯一时构建会停止。命令行的`extra_videos`可显式覆盖补充视频目录。

## 构建环境

- Python 3.11或更新版本，以及 `requirements-build.txt` 中的依赖。
- JDK17、Android SDK35/build-tools35.0.0、Gradle8.9、Chaquopy17.2.0。
- Zig ARM32交叉工具链。
- 支持CRI USM和HCA的FFmpeg；当前配置使用9.0.2。
- vgmstream命令行解码器，将7.x语音转换为旧Wwise可用的PCM。

`tools_root`包含 `jdk/`、`sdk/`、`gradle/gradle-8.9/`、`gradle-user/`、`android-user/` 和 `python311/tools/python.exe`。Windows上的Gradle工具路径使用本地或映射盘符。工具链及Gradle依赖需预先准备；工具不属于游戏输入。

签名密码通过环境变量 `BH3_KEYSTORE_PASSWORD` 和 `BH3_KEY_PASSWORD` 提供。保留自己的签名密钥用于覆盖升级。

可选 `wheelhouse` 指向完整的Android Python离线依赖集合；运行环境使用Python3.11、numpy1.26.2、tzdata2025.2。未设置时按Chaquopy配置解析依赖，详见[官方说明](https://chaquo.com/chaquopy/doc/current/android.html#requirements)。

## 独立数据阶段

仅生成基础表与材料导航：

```console
python -B -m packager build --target data --config packager.example.json
```

生成应用项目规则后的251张有效服务端表：

```console
python -B -m packager build --target tables --config packager.example.json
```

`stage_ratios`可选 `baseline` 或 `repaired`，默认保留基线的六关比例。数据阶段不产生APK；完整运行包还包括派生目录和客户端配套输出。

## 继续构建

保留失败或尚未完成的工作目录，通过原始输入入口继续：

```console
python -B -m packager.original --config packager-original.example.json --resume
```

同一轮构建可以用 `--reuse-data <目录>`复用明确选定的、由原包生成且完成的 `tables` 阶段。改变输入或表单规则时使用新的工作目录。完成的编译和转换阶段按构建记录复用，避免重复处理大型资源。

`python -B -m packager verify --work-dir <数据目录>`用于主动重新核对数据阶段产物；正常构建不反复执行整包回读。

## 配方与额外规则

- `rules/table-adaptations.json`：稀疏字段修改；新增游戏行从2.4输入投影。
- `rules/generated-data-recipes.json`：从生成表选择、关联和修改数据，不携带完整游戏表。
- `rules/native-armv7.json`：绑定原库指纹的差分兼容补丁。
- `rules/client-resource-splices.json`：针对提取结果的兼容差分。
- `rules/voice-events.json`：当前支持的语音路由标识。
- `rules/commission-rarity.json`：维护者确认随附的独立稀有度兼容规则，来源单独注明。

其他生成工具位于根目录及`scripts/`，依赖索引见`profiles/legacy-dependencies.json`。
