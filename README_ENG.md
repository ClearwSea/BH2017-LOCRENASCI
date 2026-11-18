<div align="center">
  <img src="docs/assets/logo.png" alt="BH2017-LOC-RENASCI Logo" width="164"><br>
  <h1>BH2017-LOC-RENASCI</h1>
  <p>A local compatibility runtime for the BH3_CN Android V1.9 client, featuring a Python local server, cross-version table recovery, native patches, and an offline builder.</p>

[简体中文](README.md) | English

  <p>
    <img src="https://img.shields.io/badge/platform-Android%20ARM32-007ec6" alt="Platform">
    <img src="https://img.shields.io/badge/runtime-Python-3776ab" alt="Runtime">
    <a href="https://github.com/ClearwSea/BH2017-LOCRENASCI/releases"><img src="https://img.shields.io/github/v/release/ClearwSea/BH2017-LOCRENASCI" alt="Latest Release"></a>
    <a href="https://github.com/ClearwSea/BH2017-LOCRENASCI/releases"><img src="https://img.shields.io/github/downloads/ClearwSea/BH2017-LOCRENASCI/total" alt="Total Downloads"></a>
    <a href="LICENSE"><img src="https://img.shields.io/github/license/ClearwSea/BH2017-LOCRENASCI" alt="License"></a>
  </p>

  <p>
    <a href="https://github.com/ClearwSea/BH2017-LOCRENASCI/releases">📥 Latest Release</a> ·
    <a href="#-choose-how-to-use-it">🚀 Quick Start</a> ·
    <a href="#-windows-builder-first-use-and-updates">🧱 Windows Builder</a> ·
    <a href="#-source-map-tested-devices--references">📖 Docs &amp; Source</a> ·
    <a href="docs/agent-guide.en.md">🤖 Agent Guide</a> ·
    <a href="https://github.com/ClearwSea/BH2017-LOCRENASCI">⭐ Star on GitHub</a>
  </p>
</div>

---

## What is BH2017-LOC-RENASCI

**BH2017-LOCRENASCI** is a local-runtime and compatibility source project for the Android 1.9 client. The repository provides a **local server written in Python** by this project, cross-version table recovery, client patches, resource-processing code, and Android startup components.

You can study and modify this code directly, hand the repository to an Agent for collaborative development, or use the existing scripts and command line to generate the data and application you need. The Windows offline builder provides a graphical interface and is distributed as a **base package plus a main package** through [Releases](https://github.com/ClearwSea/BH2017-LOCRENASCI/releases). See the [changelog](CHANGELOG.md) for the latest fixes and validation scope.

> [!NOTE]
> - This project was developed mainly by **VIBECODING**. The code may contain problems; please bear with them. Developers are welcome to read, verify, and improve it.
> - The project in this repository does not represent the latest development progress; developers can extend it and create their own branches from this base.
> - **AI / LLM / Agent Entry**: First read the [Agent guide: building and playing](docs/agent-guide.en.md) ([中文](docs/agent-guide.md)). Follow the separate base/main-package workflow to help users prepare inputs, build, install, and play. (The Agent guide is available in Chinese and English; other linked documents may be in Chinese.)

## ✨ Core Features

- **Python Local Server**: Custom local protocol handling, business logic, caching, and local data controls (`src/server19.py` and business modules).
- **Cross-Version Table & Resource Adaptation**: Recovers tables from a 2.4 reference client into the 1.9 structure, and converts 7.x PC audio/video assets for mobile use.
- **Android Startup Launcher & Tools**: Includes the startup screen, ARM32 Python hosting layer, save editing, backup history and export, normal 1× or assisted 20× damage toggle, and local server settings for the next Memorial Arena bosses and Abyss temperature.
- **Dual-Mode Builder**: Supports both a Windows GUI (`launch_gui.py` / `构建器.exe`) and CLI (`python -m packager`) to recover tables, apply project rules, apply compatibility patches, convert resources, and assemble the APK.
- **Split Base + Main Package Updates**: Keeps the offline toolchain and import launcher in the base package while distributing project updates via main package ZIPs with integrity/compatibility checks and rollback ("恢复上一版").

## ⚠️ Important Notes & Boundaries

> [!CAUTION]
> **Assets & License Boundaries**
>
> This repository **does not provide** the original game client or the complete game resource packages. The game client, complete official tables, native libraries, and audio/video come from external inputs. Supplemental images are made from official assets, and five CGs are taken from extractions of other official versions. They load as a separate supplemental resource pack, do not enter the source tree, the builder's built-in resources, or CI, and the project source license does not apply to them.

> [!WARNING]
> **Save Files & Signing Key Retention**
>
> - **No automatic backup on save replacement**: A replacement save selected on the startup screen is imported when the game starts, without another confirmation or an automatic backup; export the current save first if needed.
> - **Retain signing keys**: Covering updates keep the same signature. Signing keys, paths, and logs remain in `user-data/` when switching main packages; when migrating from an older all-in-one builder, preserve and copy the old `user-data/` (especially the original signing key in `user-data/keys`).

> [!TIP]
> **Local Disk Space Planning**
>
> Reserve an extra **20 GiB** of free space for one full build, covering extraction, conversion, intermediate APKs, and the finished package. Keeping results from multiple builds calls for **more than 30 GiB**. The original client packages, full 7.x resources, and tool packages are counted separately. If everything is on the same disk, plan for the actual size of inputs and tools plus 20 GiB. Details: [space reservation](docs/build.md#本地空间).

## 🚀 Choose How to Use It

| Approach | Where to start |
| --- | --- |
| **Use the Windows graphical builder (Recommended)** | Import the main package, choose the client, resources, and tools, then generate an APK and a video pack. See the [desktop builder](docs/desktop-builder.md) |
| **Use the command line and generation scripts** | Recover tables, generate runtime data, or assemble an APK (`python -m packager`). See [build and inputs](docs/build.md) and the [packager interface](src/packager/README.md) |
| **Read, modify, and extend it yourself** | Read the [source and development entry](docs/roadmap.md), then change the server, rules, patches, or resource processing by module |
| **Develop with an Agent** | Use the repository as the working directory and provide the goal and input versions. Entry points: [development conventions](AGENTS.md) and the [documentation index](docs/README.md) |

## 🧱 Windows Builder: First Use and Updates

Builder packages, supplemental inputs, and generated game files serve different purposes:

| File | Purpose | Update policy |
| --- | --- | --- |
| `BH2017-LOCRENASCI-Builder-Base-Windows-x64.zip` | **Base**: import launcher, Python, Android toolchain, audio/video tools, and companion third-party materials | Download initially; update when required by a toolchain or launcher change |
| `BH2017-LOCRENASCI-Builder-Main-v<version>.zip` | **Main**: the release's complete project program, build UI, server, rules, and patch sources | Download the desired release and import it; intermediate main-package versions are unnecessary |
| `BH2017-LOCRENASCI-Supplements-v<version>.zip` | **Supplements**: images and older CGs supplied as build inputs | Use the version specified in the release; compatible older packs can be reused (layout in [assets/README.md](assets/README.md)) |
| `client-videos.zip` | **Phone video pack**: produced by a build | Pair it with the generated APK and select it on the phone's startup screen |

- **First use**: Extract the base to a short path on the C: drive (such as `C:\BH3Builder`; a deeply nested path may prevent Android tools from starting) → run `构建器.exe` → click “导入构建主包” and select the main ZIP (manual copying over the program directory is unnecessary) → click “打开构建界面” → choose the required inputs and build.
- **Subsequent updates & rollback**: Keep the base and import the new main package. The launcher checks package integrity and toolchain compatibility; if incompatible, update the base as directed by that release. “恢复上一版” switches back to the previous main package. Signing keys, paths, and logs remain in `user-data/` when switching packages.
- **Migrating from an old all-in-one builder (e.g., V0.1.6)**: Obtain the new base, preserve and copy the old `user-data/` into its root, check tool/output paths, and import the main package. Retain the original signing key in `user-data/keys`.

## 📦 Materials & Running the App

Reading and modifying the source can start immediately. A full Android application build needs the inputs below. When developing a single module, prepare only that module's data dependencies:

| Input | Purpose |
| --- | --- |
| **1.9 client APK** | Game package base, protocol, and native libraries |
| **2.4 reference client APK** | Extract tables and required client resources, then convert them to the 1.9 structure |
| **7.x PC Windows resource directory** | Voice and video. Choose the `StreamingAssets` directory that directly contains `Audio/` and `Video/` |
| **Separate supplemental resource ZIP** | Companion images and supplemental older CGs, as specified by the selected release and [supplemental resource format](assets/README.md) |
| **Compatible save** | Import an existing save after installation, or create one with the startup screen’s built-in editor |

Users supply the client and 7.x resources themselves. [Build and inputs](docs/build.md) describes versions, directories, and tool requirements.

**Generate and run**: The graphical builder outputs `崩坏3·2017 独立版.apk` and a `client-videos.zip` from the same run (command-line output paths are in the [build notes](docs/build.md)). Install the generated APK, select the video pack from the same build on the startup screen, and import a compatible save or create one with the built-in editor before starting the game. When using the graphical builder, leaving the key path empty generates a local key and reuses it (see [signing notes](docs/desktop-builder.md#签名)). The game and the Python runtime use **ARM32**; device requirements are in [Android compatibility notes](docs/android-compatibility.md).

## 📚 Source Map, Tested Devices & References

<details>
<summary>🧭 Source Map & Repository Layout (Click to expand)</summary>

| Location | Contents |
| --- | --- |
| `src/server19.py` and business modules | Python local server, protocol handling, business logic, and cache |
| `src/rules/`, `src/profiles/`, and project configuration | Business rules, field mapping, input references, and version adaptation |
| Generation modules in `src/`, `src/scripts/`, and `src/tools/` | Table recovery, client patches, resource conversion, and assembly tools |
| `src/android-server-probe/` | Android startup screen, Python hosting layer, and save management |
| [`src/packager/`](src/packager/README.md) | Command line, GUI, and build-stage scheduling (root `launch_gui.py` is the GUI entry) |
| `configs/` | Example build configurations |
| [`docs/`](docs/README.md), `src/tests/` | Usage and development documents, and isolated check code |

Further reading: [Feature scope](docs/status.md) · [Source and development entry](docs/roadmap.md) · [Data and rule sources](docs/data-sources.md)

</details>

<details>
<summary>📱 Tested Devices (5 devices tested by maintainer)</summary>

The following devices were actually tested by the maintainer and are listed for reference; devices not listed here are not guaranteed to behave the same.

| Device | OS | SoC | RAM |
| --- | --- | --- | --- |
| SONY SOV36 | Android 8.1 / Android 9 (official near-stock) | Snapdragon 835 | 4 GB |
| Razer Phone 1 | Android 9 (official near-stock) | Snapdragon 835 | 8 GB |
| Razer Phone 2 | Android 9 (official near-stock) | Snapdragon 845 | 8 GB |
| OPPO PDRM00 | Android 12 | Snapdragon 865 | 8 GB |
| OnePlus PJZ110 | Android 15 (`PJZ110_15.0.0.860(CN01)`, system built-in Tango translation layer) | Snapdragon 8 Elite | 16 GB |

</details>

<details>
<summary>🔎 Client Reference Information (Third-party links)</summary>

This repository does not provide the original game client or the complete game resource packages. The following third-party information was found by the maintainer on the public internet and is for reference only. Content, versions, and availability come from the original publishers. This project does not guarantee them.

| Reference | Third-party information |
| --- | --- |
| V1.9 | [BV1UU4u6yE8R](https://www.bilibili.com/video/BV1UU4u6yE8R/) |
| V2.4 demo | [BV1zJ411N7Qz](https://www.bilibili.com/video/BV1zJ411N7Qz/) |
| V7.0 client | [BV1xCpPezEeM](https://www.bilibili.com/video/BV1xCpPezEeM/) |

</details>

## 🔗 Related Projects

- **[BH-LOCRENASCI-ACT-EDIT](https://github.com/ClearwSea/BH-LOCRENASCI-ACT-EDIT)**: Companion offline save editor for BH3 V1.9 (Python / Tkinter, Windows single-file EXE), compatible with the launcher's save import/export.

## ❤️ License & Acknowledgements

This project's own source is under the [MIT License](LICENSE), copyright **ClearwSea**. License notes for third-party dependencies and external assets are in [NOTICE](NOTICE.md). Origins of configuration and assets are in [data and rule sources](docs/data-sources.md).

Thanks to the developers who took part in development, research, testing, and feedback, and to ChatGPT, DeepSeek, Claude, and Gemini for help with coding, analysis, and documentation.
