# 依赖与源码入口

基础表导出使用主机Python和Capstone5.0.9，见requirements-build.txt。Android承载层使用Python3.11、numpy1.26.2、tzdata2025.2，见requirements-runtime.txt及Gradle配置。

| 工作 | 额外依赖 |
| --- | --- |
| Android承载层与DEX | JDK17、Android SDK35、Gradle/Chaquopy，插件版本见构建文件 |
| ARM辅助库 | Zig/ARM编译器；工具获取说明见server19_arm_toolchain.py |
| APK交付 | zipalign、apksigner及构建者自己的密钥 |
| 原生指令验证 | Unicorn2.1.4、Capstone5.0.9，见requirements-native-checks.txt |
| Unity资源与图像处理参考实现 | UnityPy、Pillow |
| Lua能力与温度配方参考实现 | Lupa |
| 离线温度曲线研究 | Matplotlib、NumPy |

后四类按具体配方选用，构建环境应固定实际使用的依赖版本。工具链与第三方二进制不随源码提供。

Android目录内的server_entry、probe_entry由承载层Python模块提供，java模块由Chaquopy提供。服务端运行核心与根目录兼容模块的本地导入源码均包含在仓库中。运行配方检查前，请按该配方的要求准备原生库、生成数据和资源输入。
