# Agent guide: help the user build and play

[中文](agent-guide.md) · [English](agent-guide.en.md)

**Document version date: 2026/11/10. This guide may lag behind the actual project.** Before acting, carefully compare it with the current repository, selected commit, release notes, configuration examples, and actual file layout—especially supported platforms, required inputs, tool paths, command arguments, and save compatibility. When they differ, follow the verified project state and promptly tell the user which instructions are outdated and how you will adjust. Explicitly identify anything you cannot confirm. Do not treat this guide as a permanently valid command list. If you cannot check online, explain that your conclusions are limited to the local version.

Assume you already have this repository's address and have started reading this guide, regardless of your vendor or Agent environment. Do not ask the user to provide an address you already know. Your task is to help them build, prepare a save, install, and start playing using their device and available materials. Explain the next step in language they understand. Perform work you can complete within the authorized environment; when materials are missing, say exactly what is needed, why, and how work will continue once provided.

This guide covers the public ARM build workflow. First read the selected version's [README](../README_ENG.md), [development conventions](../AGENTS.md), [changelog](../CHANGELOG.md), and [release](https://github.com/ClearwSea/BH2017-LOCRENASCI/releases). Behavior is determined by that version's source and release notes. Do not present unpublished branches, test records, or progress on other architectures as shipped features.

This guide does not pin a builder or save-editor release. Select according to the official releases and compatibility requirements available at the time, and record the actual version. The supplement pack may have a different version from the builder; follow the selected release's instructions. The numbers 1.9, 2.4, and 7.x below identify game-resource input versions, not project releases to download. Check them against the current configuration too.

## How the three projects work together

| Repository | Guide |
| --- | --- |
| BH2017-LOCRENASCI | [Android building and playing](agent-guide.en.md) |
| BH-LOCRENASCI-ACT-EDIT | [Save creation, editing, and restoration](https://github.com/ClearwSea/BH-LOCRENASCI-ACT-EDIT/blob/main/docs/agent-guide.en.md) |
| BH-NX-Ferculum | [NS building, integration, and validation](https://github.com/ClearwSea/BH-NX-Ferculum/blob/main/docs/agent-guide.en.md) |

Follow the guide for the current goal; installing all three repositories is unnecessary. Use the editor when a save is needed, then return to the target platform’s game guide. Do not request usable materials again. Carry forward the user’s platform, versions, file paths, goal, and authorization rather than restarting the questions. Cross-project guides do not replace checks of actual version and interface compatibility.

## Before starting: communication and network checks

### Explain progress in language the user understands

Assess familiarity from the user's questions and feedback without labeling them as having “low technical ability.” If they are unfamiliar with building, signing, or file paths, **at every step** briefly explain what you are doing, why, what currently blocks progress, what they need to do next, and any precautions relevant to that step. If nothing is blocked or no user action is needed, say so. Do not invent problems or overwhelm them with a complete technical manual.

Ask necessary questions before reaching a step that depends on a user decision or missing material, rather than after it fails. Start with their device and available materials. Before downloading, explain file size and destination. Before installation, establish whether this is a new install or an update and whether the save is backed up. Before generating a save, explain starter and max-level experience templates. Ask only a few questions needed for the current and immediately following step. Reuse answers and authorization already given; inspect what you can yourself first. While waiting, continue work that does not depend on the answer.

For example: “I'll check download speed first because the build tools are large, so we don't discover a connection problem halfway through. You don't need to do anything yet. Next, please tell me how much free disk space you have, or let me check it directly.” If the network is blocked, explain the impact and alternatives rather than just displaying an error or telling the user to solve it themselves.

### Test the actual download environment; do not assume a reliable proxy

Assume the user's Agent **does not have a reliable network proxy**. Before downloading large files, use available tools for a quick check with time and traffic limits. Being able to read the repository does not prove that large release assets download reliably. An Agent's cloud connection also does not represent the user's computer connection.

1. In the environment that will actually download the files, test the repository/release page or GitHub API. Record response status and elapsed time. A connection timeout of about 10 seconds and a total request limit of about 20 seconds are reasonable starting points. Retry only a limited number of times.
2. Obtain a real asset URL from actual release metadata and follow redirects to test downloading. Prefer a small sample of about 1–4 MiB, with an approximately 20-second total timeout and a hard byte limit. Record bytes received, average speed, and interruptions. Stop at the limit even if the server ignores Range; do not turn a speed test into a full download. A HEAD request alone does not measure download speed.
3. Estimate download duration using the actual asset size. Repeated timeouts, interrupted transfers, or sustained speeds below roughly 200 KiB/s for a large package are examples of poor quality, not rigid pass/fail thresholds. Distinguish authentication errors, API rate limits, and expired or invalid links from network problems.
4. If you cannot make network requests, say that you could not test. Give the user short executable instructions or commands and explain what results to return. Do not fabricate a successful check.

If the connection is poor, **explicitly tell the user: “The current environment has a poor connection to GitHub,”** supported by measured timeouts, speed, or estimated waiting time. This can occur on some networks in mainland China, but location alone is not evidence. Also explain which downloads remain necessary and what preparation can continue.

Then proactively devise and try a workable way to obtain the release. Do not merely tell the user to “find a proxy.” Choose based on your tools and their environment: official direct asset links, a downloader with resume support, an existing user-approved proxy or alternate network, downloading through the browser and handing the file to the Agent, or downloading in another authorized environment and transferring it back. When user participation is necessary, explain the approach, why it can help, and the specific step they need to take.

This guide does not prescribe a permanently valid mirror or proxy address. If a third-party relay is necessary, verify availability and disclose the source first. Do not send it GitHub credentials, signing keys, or saves, and do not disable TLS certificate validation. Check downloaded files against official SHA-256 values when provided. If an official checksum is temporarily unavailable, mark verification as pending rather than claiming the file is trusted. Proxy installation, system setting changes, and paid services require the applicable user authorization; download problems do not authorize unrelated environment changes.

## 1. Understand the intended result

This project combines user-supplied game clients and resources with the repository's Python local server, compatibility patches, and Android startup components to build an offline version for compatible Android devices. During normal play, the server runs locally on the phone as part of the APK. There is no need to rent a server or keep a Python service running on a computer.

Deliver three items:

| File | Source and purpose |
| --- | --- |
| Game APK | Generated by this project; install it on the phone |
| `client-videos.zip` | Generated in the same build as the APK; select it on the phone's startup screen. It is not the supplement pack downloaded before building |
| `account.json` | An existing compatible save or one generated by the companion save editor; select it on the phone's startup screen |

Repository source, the Windows builder ZIP, and the external supplement ZIP cannot be installed as game APKs. Downloading the source does not provide the original game resources.

If the user supplied only the repository link without a goal, briefly explain this purpose and ask whether they want to build and play or modify the source. If they already said they want to play, continue without requiring them to learn the code structure.

## 2. Collect only the necessary information

Inspect the supplied files and environment first, then ask for missing information in batches appropriate to the current step. The following is information the Agent needs, not a questionnaire to dump on a beginner:

- Computer OS, free space, and permitted build/output directories.
- Phone model and Android version; new installation or an existing installation.
- Whether the 1.9 APK, 2.4 APK, and 7.x PC Windows resources are available, and their actual paths.
- Whether a compatible save exists; whether a new player wants a starter account or a max-level experience account.
- For an update, whether the original signing key and save have been retained.

Prefer the released Windows x64 offline builder by default. Other desktop operating systems do not have an equivalent ready-made verified workflow. Do not simply rewrite Windows paths as Linux/macOS paths and claim support. A web-only chat environment can provide instructions; if local commands cannot be executed, state this and guide the user through the corresponding local action.

The public game's runtime and Python runtime use ARM32. “Snapdragon,” “64-bit,” or an Android version alone does not establish compatibility. The device needs native ARM32 support or working system-level translation. See [tested devices](../README_ENG.md#tested-devices) and [Android compatibility](android-compatibility.md). The project does not install or provide TANGO. Do not promise playability on unlisted devices, emulators, or other architectures.

Reserve **20 GiB** beyond the inputs and tools for a full build; retaining multiple builds calls for **more than 30 GiB**. The phone also needs room for APK installation, embedded-resource extraction, and video import. Assess phone storage using actual file sizes rather than applying the computer's space requirement.

## 3. Obtain the release and materials

Visit the [main project's releases](https://github.com/ClearwSea/BH2017-LOCRENASCI/releases), read the selected release notes, and record its version and asset names. Prefer a stable release for playing. If a developer explicitly chooses a branch, record its commit and explain how it differs from the released builder.

| Material | Preparation and checks |
| --- | --- |
| Windows builder | Download `BH2017-LOCRENASCI-Builder-Windows-x64-<version>.zip`, check download integrity against `SHA256SUMS.txt` if supplied, and extract it completely |
| 1.9 client APK | Supplied by the user; provides the base game package, protocol, and native library |
| 2.4 reference client APK | Supplied by the user; provides tables and resources for extraction and adaptation |
| 7.x PC Windows resources | Select the `StreamingAssets` directory directly containing `Audio/` and `Video/`; voice data is under `Audio/GeneratedSoundBanks/Windows/` |
| External supplement ZIP | Download the asset specified by the selected release and its compatibility requirements. At this guide's date it supplies seven images and missing older CGs; use the current resource specification for the actual layout |

Get the supplement download URL from the selected release's body or asset list. If the notes refer to an older supplement version, use that version. Do not guess or construct download URLs from the builder version number.

Original clients and complete 7.x resources are not included in the repository or builder. **The Agent must explicitly request the 1.9 client APK, 2.4 reference client APK, and 7.x PC Windows client resources from the user.** Inspect files already supplied and do not request usable materials again. Name each missing item; do not merely say “prepare the materials” and wait.

If the user does not know what these are, where to find them, or how to proceed, read the [README's third-party references](../README_ENG.md#client-reference-information) and directly provide the Bilibili links and BV identifiers. Do not simply tell them to browse the README. At this guide's date, the references are:

| Required material | Bilibili reference video |
| --- | --- |
| 1.9 client APK | [BV1UU4u6yE8R](https://www.bilibili.com/video/BV1UU4u6yE8R/) |
| 2.4 reference client APK (demo) | [BV1zJ411N7Qz](https://www.bilibili.com/video/BV1zJ411N7Qz/) |
| 7.x PC Windows client resources (7.0 reference) | [BV1xCpPezEeM](https://www.bilibili.com/video/BV1xCpPezEeM/) |

Check the current README for updated links before providing them. Explain that these are third-party reference videos: the user needs to obtain the corresponding clients or resources following the videos and their descriptions, **not download the videos themselves**. Verify current content and resource availability; do not present a video page as a verified direct download. If an entry is unavailable or the user cannot find the resources, identify what is missing and continue helping. Do not invent URLs or substitute other versions or previously built APKs.

Explicitly ask the user to download and provide these materials. Based on their actual computer and confirmed workspace, give a concrete folder path and explain where each item goes. For example, put the two APKs and 7.x resources under the confirmed workspace's `inputs/`. If the directory does not exist and creation is authorized, create it yourself. Do not give a beginner an unresolved `<path>` placeholder.

Accept other methods supported by the environment: an existing absolute file path, an upload, an accessible shared location, or a download link. Do not require large files to be moved again just to match the example layout. Explain which methods you can actually access; when chat uploads have size limits, prefer local paths or other accessible methods.

For example: “I still need three items: the 1.9 APK, the 2.4 APK, and the 7.x PC game resources. The three videos above are references from the README; follow their descriptions to obtain the files. Put them in the folder I specified, or tell me where they already are. If you have an archive, give me its path first and I'll inspect it and determine whether extraction is needed. You don't need to identify the code inside.” Once received, inspect APKs, resource directories, and version layouts, and locate the `StreamingAssets` directory containing `Audio/` and `Video/`. Do not leave these technical judgments to a beginner.

Reference hashes and sizes for original APKs/supplement ZIPs are advisory; a mismatch does not automatically prevent building. Internal native-library fingerprints, instruction preimages, table structures, and required files must pass validation and must not be bypassed. The 7.x reference comparison uses filenames and sizes. See [supplement format](../assets/README.md).

## 4. Windows builder: the preferred path for playing

The fully extracted package should have this main layout:

```text
BH2017-LOCRENASCI-Builder/
  构建器.exe
  app/                   Project source and configuration
  tools/                 Offline toolchain
    python/python.exe
    android/
    zig/
    ffmpeg/
    vgmstream/
    wheelhouse/
  user-data/             Settings, logs, and signing keys created during use
  output/                Default output location; another may be selected
```

1. Double-click `构建器.exe`, or run the PowerShell command below from the package root.
2. Select the 1.9 APK, 2.4 APK, 7.x `StreamingAssets`, and supplement ZIP.
3. For the offline tool directory, select `tools/` at the package root—not `tools/android/` or the source tree's `src/tools/`.
4. Keep output separate from `app/`, input resources, and tools. Do not place output inside them or make it their parent directory.
5. Configure signing, click “检查路径” (Check paths), then “开始构建” (Start build) once checks pass, and monitor the log.

```powershell
.\tools\python\python.exe -B -s .\app\launch_gui.py .
```

For a new installation without a personal key, all four signing fields may be left blank. The builder creates and reuses `user-data/keys/local-build.jks`, with default alias `builder` and password `android`. Updating an existing installation requires its original key, alias, and passwords. Generating another key with the same name does not reproduce the original signature.

Back up `user-data/keys` and personal settings separately for future updates. Do not place personal keys, passwords, or saves in public repositories or redistributed builder ZIPs.

After success, the timestamped subdirectory under the output directory contains:

```text
崩坏3·2017 独立版.apk
client-videos.zip
build-result.json
build-config.local.json
work/original-build.json
work/logs/
```

The GUI and command line use the same full build workflow. The builder does not automatically download missing dependencies. If offline tools are incomplete, first check extraction layout and package integrity. See [desktop builder](desktop-builder.md) for signing details.

## 5. Building through the Agent's command line or modifying source

If you can operate local files and commands, use the source entry point directly rather than needing to click through the GUI. Prefer reusing the released package's toolchain. Cloning source alone does not supply tools or game inputs.

Read the [configuration example](../configs/packager-original.example.json) and [packager interface](../src/packager/README.md). Copy the example to a personal configuration, such as `configs/packager-original.local.json`, and fill the fields below using actual locations. Prefer `/` in JSON paths. Relative paths resolve against the **configuration file's directory**; absolute paths are also supported.

| Field | Value |
| --- | --- |
| `schema` / `mode` | `1` / `original-inputs` |
| `client19` / `client24` | Actual paths to the two original APKs |
| `resources7x` / `supplements` | `StreamingAssets` directory / supplement ZIP or extracted directory |
| `tools_root` | Package `tools/android`; different from the GUI's tool-directory field |
| `zig` | `tools/zig/zig.exe` |
| `ffmpeg` | `tools/ffmpeg/ffmpeg.exe` |
| `voice_decoder` | `tools/vgmstream/vgmstream-cli.exe` |
| `wheelhouse` | `tools/wheelhouse`; explicitly set when using the offline package |
| `keystore` / `key_alias` | Existing signing file / corresponding alias |
| `work_dir` | A dedicated, not-yet-existing directory for this build, separate from source and inputs |

Run the following from the source root. Assign `$builderPython` to the actual absolute path of the package's `tools/python/python.exe`. If tools and source are in different locations, do not blindly copy relative tool paths.

```powershell
& $builderPython -B -m packager build --target apk --config .\configs\packager-original.local.json
```

Before execution, supply `BH3_KEYSTORE_PASSWORD` and `BH3_KEY_PASSWORD` as environment variables to the build process. Do not place passwords in public configuration, command-line arguments, or logs. The command-line entry does not create a signing key automatically. On a first build, either create it through the GUI or use the package JDK's `keytool.exe`; the path and alias must match the configuration.

For example, when creating a new key for a **new installation**, first set those two environment variables. Set `$keytool` to the actual `tools/android/jdk/*/bin/keytool.exe` and `$keystore` to a destination file that does not yet exist, then run:

```powershell
& $keytool -genkeypair -noprompt -storetype JKS -keystore $keystore -alias builder -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=Offline Local Build" -storepass:env BH3_KEYSTORE_PASSWORD -keypass:env BH3_KEY_PASSWORD
```

A full build performs table recovery, native patching, runtime-data generation, client-resource processing, voice/video conversion, Android compilation, APK composition, alignment, and signing. Command-line outputs under `work_dir` are `candidate.apk`, `embedded/client-videos.zip`, `original-build.json`, and `logs/`.

On failure, first inspect the failed stage in `original-build.json` and its log. If configuration, inputs, and source are unchanged and the recorded status is `failed` or `incomplete`, resume that task:

```powershell
& $builderPython -B -m packager.original --config .\configs\packager-original.local.json --resume
```

Do not use `--resume` on successful builds or blindly reuse stages after changing inputs or source. When rebuilding, preserve necessary outputs and failure evidence, then use an explicitly chosen new work directory. Do not indefinitely retain complete large build sets for every small fix. `--target data` and `--target tables` generate data only, not an installable APK.

Follow `AGENTS.md` before modifying source. See the [development entry](roadmap.md) for modules. Run appropriate regression checks and record build success separately from actual gameplay validation on a phone.

## 6. Prepare a compatible save

Users with an existing project save may continue using it. New players can obtain the editor from [BH-LOCRENASCI-ACT-EDIT releases](https://github.com/ClearwSea/BH-LOCRENASCI-ACT-EDIT/releases) and read its [Android instructions](https://github.com/ClearwSea/BH-LOCRENASCI-ACT-EDIT/blob/main/docs/使用方式-Android.md). It edits the companion offline version's `account.json`; it does not convert official online accounts.

Select a template, click “使用模板新建” (Create from template), and save to a new file:

- **Starter account (“新号”):** begins with level-1 White Comet. To watch the opening CG and enter the first stage, first verify that both the selected editor and Android build support the opening flow, then enable “首次登录” (First login) on a level-1 starter account. At this guide's date it is unchecked by default. Follow the current version's options and compatibility requirements.
- **Max-level experience account (“满级体验号”):** for trying characters, equipment, and stages. Template progress and equipment coverage follow the editor's documentation; inclusion does not mean all content has been fully tested.

Save as `account.json` for easy identification. Preserve the original save and never overwrite the user's only copy. Changing captain level alone does not also upgrade characters or equipment and may not match tutorial progress. Prefer an unmodified starter or experience template for a first playthrough.

## 7. Install and start playing

1. Transfer the APK, same-build `client-videos.zip`, and `account.json` to accessible locations on the phone.
2. Install the APK for a new installation. Before updating, follow the backup instructions below and confirm the original signing key is used.
3. On the startup screen, tap “选择资源包” (Select resource pack) and select `client-videos.zip`. Do not select the Windows builder ZIP or supplement ZIP. Manual video-pack extraction is unnecessary.
4. Tap “选择存档” (Select save) and choose `account.json`. Existing imported resources and saves may be reused. Selecting another save prompts for replacement when starting the game; establish whether existing progress needs preservation first.
5. Choose damage mode: assisted **20×** is enabled by default; disable it for normal **1×**. Fully exit and reopen the application after changing it.
6. Tap “开始游戏” (Start game) and wait for resource preparation and the local service. Observe status during first-time preparation; do not clear data or uninstall solely because it takes time.
7. In the companion offline login screen, any username and password may be entered; they are not checked locally and no official account is required. Automatic starter opening playback depends on the chosen template.

If device tools are available and installation is authorized, inspect connected devices and operate the intended one; specify the target when several are connected. Build authorization alone does not authorize replacing the phone's save. If you cannot operate the phone, give the user these steps and ask which screen they reach.

Before delivery, verify a successful build receipt and the presence of the APK and video pack, and record file sizes and SHA-256 values. Ask the user to verify at least entry to the bridge or starter opening, entry and completion of an ordinary stage, and persistence of progress after restarting. If no device test was performed, state “Build successful; device validation pending.”

## 8. Updates, backups, and rollback

Before updating, use “导出当前存档” (Export current save) on the startup screen and confirm the backup is outside the application's directory. Internal old-save backups are deleted on uninstall and cannot be the sole backup before uninstalling.

Build the new APK with the original signing key and install it over the existing application. Provide the video pack from that build. Updating the desktop builder alone does not update the phone's installed game. If signatures differ, look for the original key first rather than immediately uninstalling. If a new signature is unavoidable, verify a recoverable external save backup and let the user decide whether to uninstall.

Keep the current working APK, corresponding video pack, signing key, and necessary saves. Check save compatibility before rollback too; a save written by a newer version is not guaranteed to work with an arbitrary older version.

## 9. Troubleshoot from evidence

| Symptom | First checks |
| --- | --- |
| Original clients or complete resources are missing | They are not included in the repository or builder; explain missing inputs and provide the README reference entries |
| The 7.x directory lacks Audio/Video | Select `StreamingAssets` directly containing both, not the parent game directory |
| Offline tool package is incomplete | Confirm complete extraction, GUI selection of `tools/`, and CLI `tools_root` pointing to `tools/android/` |
| Native fingerprint or patch preimage mismatch | Check whether the internal input library is supported; retain actual hashes and errors. Do not remove validation or blindly apply addresses |
| Missing CG or assets | Check supplement version/layout, 7.x coverage, and the failed stage in `original-build.json` |
| Build directory already exists | A fresh build needs a new directory; resume unfinished builds only under the stated conditions. Do not delete all history |
| APK installation fails or signatures conflict | Check phone ABI, installation error code, storage, and original signing key; protect saves first |
| Startup fails or waits indefinitely | Read the actual startup error and local-service logs; check resources and device compatibility. Distinguish import failure from service failure |
| Story, character, or equipment actions fail or freeze | Record version, device, characters/equipment, stage/difficulty, action sequence, and whether reproducible or intermittent |

For build problems, collect stage logs and receipts. For game problems, collect screenshots and reproduction steps, plus logcat when available. Request a save only when needed for diagnosis and with the user's consent, removing personal information. Check [existing issues](https://github.com/ClearwSea/BH2017-LOCRENASCI/issues) first. Do not post or close issues for the user without instruction.

## 10. Final handoff

State the version/commit used, APK and video-pack locations, save source, signing-key backup location, and which checks passed or remain pending. Give a short explanation of how to start playing and retain build logs for troubleshooting. Downloading the repository, generating tables, or a build process merely exiting is not a complete playable delivery.

This document provides the Agent's workflow. Source-development conventions remain in [AGENTS.md](../AGENTS.md); see the [documentation index](README.md) for other topics.
