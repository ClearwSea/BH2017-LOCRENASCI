[中文](README.md) · [English](README_ENG.md)

> This README was generated automatically by an Agent; please refer to the actual project state as authoritative.

# BH2017-LOCRENASCI

See the [changelog](CHANGELOG.md) for the latest fixes and validation scope.

> This project was developed mainly by VIBECODING. The code may contain problems; please bear with them. Developers are welcome to read, verify, and improve it.

BH2017-LOCRENASCI is a local-runtime and compatibility source project for the Android 1.9 client. The repository provides a **local server written in Python** by this project, cross-version table recovery, client patches, resource-processing code, and Android startup components.

You can study and modify this code directly, hand the repository to an Agent for collaborative development, or use the existing scripts and command line to generate the data and application you need. The companion Windows builder provides a graphical interface for assembling a complete APK, and is one of the ways to use the project. The Windows offline builder can be downloaded from [Releases](https://github.com/ClearwSea/BH2017-LOCRENASCI/releases).

Features are based on the **2 November 2026** version and do not represent the latest development progress. Developers who need later features can extend this base themselves.

Linked documents in this repository are still in Chinese.

## Choose how to use it

| Approach | Where to start |
| --- | --- |
| Read, modify, and extend it yourself | Read the [source and development entry](docs/roadmap.md), then change the server, rules, patches, or resource processing by module |
| Develop with an Agent | Use the repository as the working directory and provide the goal and input versions. Entry points: [development conventions](AGENTS.md) and the [documentation index](docs/README.md) |
| Use the command line and generation scripts | Recover tables, generate runtime data, or assemble an APK as needed. See [build and inputs](docs/build.md) and the [packager interface](src/packager/README.md) |
| Use the Windows graphical builder | Choose the client, resources, and tools, then generate an APK and a video pack. See the [desktop builder](docs/desktop-builder.md) |

## Materials and disk space

Reading and modifying the source can start immediately. A full Android application build needs the inputs below. When developing a single module, prepare only that module's data dependencies.

| Input | Purpose |
| --- | --- |
| 1.9 client APK | Game package base, protocol, and native libraries |
| 2.4 reference client APK | Extract tables and required client resources, then convert them to the 1.9 structure |
| 7.x PC Windows resource directory | Voice and video. Choose the `StreamingAssets` directory that directly contains `Audio/` and `Video/` |
| Separate supplemental resource ZIP | Six companion images and five older CGs missing from the current 7.0 resources |
| Compatible save | Supplied separately and imported after the application is installed |

Users supply the client and 7.x resources themselves. [Build and inputs](docs/build.md) describes versions, directories, and tool requirements. [Supplemental resource format](assets/README.md) describes the ZIP layout.

### Client reference information

This repository does not provide the original game client or the complete game resource packages. The following third-party information was found by the maintainer on the public internet and is for reference only. Content, versions, and availability come from the original publishers. This project does not guarantee them.

| Reference | Third-party information |
| --- | --- |
| V1.9 | [BV1UU4u6yE8R](https://www.bilibili.com/video/BV1UU4u6yE8R/) |
| V2.4 demo | [BV1zJ411N7Qz](https://www.bilibili.com/video/BV1zJ411N7Qz/) |
| V7.0 client | [BV1xCpPezEeM](https://www.bilibili.com/video/BV1xCpPezEeM/) |

### Local disk space

**Suggested local space:** reserve an extra **20 GiB** of free space for one full build, covering extraction, conversion, intermediate APKs, and the finished package. Keeping results from multiple builds calls for **more than 30 GiB**. The original client packages, full 7.x resources, and tool packages are counted separately. If everything is on the same disk, plan for the actual size of inputs and tools plus 20 GiB. Details: [space reservation](docs/build.md#本地空间).

## Generate and run the application

The command line or the graphical builder can, in order, recover tables, apply project rules, apply compatibility patches, convert resources, and assemble the APK. The graphical builder outputs `崩坏3·2017 独立版.apk` and a `client-videos.zip` from the same run. Command-line output paths are in the [build notes](docs/build.md).

Install the generated APK, import the companion video pack and a compatible save on the startup screen, then launch the game. The startup screen provides resource and save management, plus a choice between normal 1× damage and assisted 20× damage.

Covering updates keep the same signature. When using the graphical builder, leaving the key path empty generates a local key and reuses it. How to fill in and back up the key: [signing notes](docs/desktop-builder.md#签名). The game and the Python runtime use ARM32. Device requirements: [Android compatibility notes](docs/android-compatibility.md).

### Tested devices

The following devices were actually tested by the maintainer and are listed for reference; devices not listed here are not guaranteed to behave the same.

| Device | OS | SoC | RAM |
| --- | --- | --- | --- |
| SONY SOV36 | Android 8.1 / Android 9 (official near-stock) | Snapdragon 835 | 4 GB |
| Razer Phone 1 | Android 9 (official near-stock) | Snapdragon 835 | 8 GB |
| Razer Phone 2 | Android 9 (official near-stock) | Snapdragon 845 | 8 GB |
| OnePlus PJZ110 | Android 15 (PJZ110_15.0.0.860(CN01), system built-in Tango translation layer) | Snapdragon 8 Elite | 16 GB |

## Source map

| Location | Contents |
| --- | --- |
| Root `server19.py` and business modules | Python local server, protocol handling, business logic, and cache |
| `src/rules/`, `src/profiles/`, and project configuration | Business rules, field mapping, input references, and version adaptation |
| Root generation modules, `src/scripts/`, `src/tools/` | Table recovery, client patches, resource conversion, and assembly tools |
| `src/android-server-probe/` | Android startup screen, Python hosting layer, and save management |
| [`src/packager/`](src/packager/README.md) | Command line, GUI, and build-stage scheduling |
| [`docs/`](docs/README.md), `src/tests/` | Usage and development documents, and isolated check code |

[Feature scope](docs/status.md) describes component responsibilities. [Source and development entry](docs/roadmap.md) describes where to make changes. [Data and rule sources](docs/data-sources.md) separates original-table derivatives, compatibility configuration, and project rules.

## Assets and license

The game client, complete official tables, native libraries, and audio/video come from external inputs. Supplemental images are made from official assets, and five CGs are taken from extractions of other official versions. They load as a separate supplemental resource pack. They do not enter the source tree, the builder's built-in resources, or CI, and the project source license does not apply to them. Compatible saves are supplied separately.

This project's own source is under the [MIT License](LICENSE), copyright ClearwSea. License notes for third-party dependencies and external assets are in [NOTICE](NOTICE.md). Origins of configuration and assets are in [data and rule sources](docs/data-sources.md).

## Acknowledgements

Thanks to the developers who took part in development, research, testing, and feedback, and to ChatGPT, DeepSeek, Claude, and Gemini for help with coding, analysis, and documentation.

## Repository layout

- `src/`: server, builder, native compatibility code, rules and tests.
- `configs/`: example build configurations.
- `docs/`: usage and development documentation.
- `launch_gui.py`: GUI entry; `python -m packager` remains the CLI entry.
