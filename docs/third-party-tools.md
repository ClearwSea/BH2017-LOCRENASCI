# 离线工具与第三方许可

完整Windows构建器ZIP包含程序源码、`src/tools/`、`LICENSES/`、`third-party-sources/`和第三方清单。解压后直接运行`构建器.exe`；工具不通过GUI下载。客户端、游戏素材、补充资源ZIP和存档由使用者另行准备。

| 组件 | 版本 | 主要许可 |
| --- | --- | --- |
| 桌面Python / Android构建用Python | 3.13.15 / 3.11 | PSF及随附第三方许可 |
| OpenJDK（Eclipse Temurin） | 17.0.20.1+1 | GPL-2.0及Classpath exception；各模块例外见legal |
| Gradle | 8.9 | Apache-2.0及所含依赖许可 |
| Android平台 / Build Tools | API35 / 34.0.0、35.0.0 | 各文件的AOSP及第三方许可，见随附NOTICE |
| Chaquopy及Android Python依赖 | 17.2.0；各包见清单 | MIT、PSF、BSD、LLVM等；libgfortran为GPL-3.0及GCC runtime exception |
| Zig | 0.15.2 | MIT及所含LLVM、libc等组件许可 |
| FFmpeg精简工具 | 9.0.2 | LGPL-2.1-or-later，未启用GPL或nonfree组件 |
| vgmstream音频工具 | 7c520e8f | ISC；Getopt及mpg123等依赖各有许可 |
| UnityPy、Pillow等桌面依赖 | 见第三方清单 | 各包的MIT、BSD、Apache等许可 |

本项目自有代码采用[MIT](../LICENSE)。工具的许可、版权与对应源码见离线包根目录`THIRD-PARTY.md`；[重建入口](../src/packager/toolchain/README.md)提供FFmpeg、vgmstream及UnityPy调整的说明。第三方许可证允许的修改、替换和重建权利按各自条款保留。

Android构建材料中的libgfortran对应Google GCC 4.9分支`f236b449daeff96112b586ed4f06980e88012d39`，源码及Chaquopy构建脚本随离线包提供。重新分发包含这些运行库的应用时，应随同保留相应许可并按条款提供对应源码材料。
