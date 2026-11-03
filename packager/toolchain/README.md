# 离线工具与重建

Windows构建器使用同级`tools/`目录中的工具。工具版本、许可证和对应源码随完整离线构建器ZIP提供，解压后见根目录`THIRD-PARTY.md`、`LICENSES/`和`third-party-sources/`。

- `rebuild_ffmpeg.sh`：从FFmpeg 9.0.2源码重建本项目使用的USM/HCA→MP4工具，关闭GPL及nonfree组件。
- `rebuild_vgmstream.py`：从vgmstream 7c520e8f源码重建Wwise音频解码器，关闭FFmpeg、G.719及G.722.1支持；保留Vorbis、MPEG、CELT、Speex、ATRAC9及内建解码器。
- `UnityPy-optional-FMOD.patch`：将UnityPy 1.25.4的FMOD导入延后到可选音频导出分支。离线工具包不附带FMOD；本项目使用的表单、AssetBundle及贴图处理不依赖该分支。

上述脚本用于重建第三方工具，日常生成应用直接使用`tools/`中的程序即可。

## FFmpeg

在Windows Git Bash或MSYS2中准备GNU make、nm及Zig 0.15.2。将源码解压到独立目录，设置`ZIG_EXE`为`zig.exe`的位置，运行：

```sh
bash rebuild_ffmpeg.sh /path/to/ffmpeg-9.0.2
```

脚本在源码目录内构建；已有构建文件时请先使用FFmpeg提供的清理目标，或使用新的源码解压目录。产物为源码目录中的`ffmpeg.exe`。

## vgmstream

Windows上准备CMake、Ninja、Git Bash和Zig 0.15.2，将对应源码解压后运行：

```powershell
python rebuild_vgmstream.py --source path/to/vgmstream-7c520e8f --build path/to/build --zig path/to/zig.exe
```

产物为构建目录`cli/vgmstream-cli.exe`。旁边保留离线工具包中的`libvorbis.dll`、`libmpg123-0.dll`、`libcelt-0061.dll`、`libcelt-0110.dll`及`libspeex-1.dll`；它们的源码版本及构建步骤见源码包`doc/BUILD-LIB.md`及`third-party-sources/`中各库。Getopt源码位于vgmstream的`ext_libs/Getopt/`，采用LGPL-2.1-or-later。

重建与替换第三方库的权利依其许可证保留；对应源码及构建说明与离线工具一起提供。项目MIT许可证仅适用于本项目自有代码。
