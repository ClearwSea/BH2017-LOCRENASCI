param(
    [string]$RuntimeZip,
    [string]$ToolsDirectory
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$tools = (Resolve-Path -LiteralPath $ToolsDirectory).Path
$env:JAVA_HOME = (Get-ChildItem -LiteralPath (Join-Path $tools 'jdk') -Directory | Select-Object -First 1).FullName
$env:ANDROID_HOME = Join-Path $tools 'sdk'
$env:ANDROID_USER_HOME = Join-Path $tools 'android-user'
$env:GRADLE_USER_HOME = Join-Path $tools 'gradle-user'
$env:SERVER19_BUILD_PYTHON = Join-Path $tools 'python311/tools/python.exe'
$project = Join-Path $repo 'android-server-probe'
$nativeOutput = Join-Path $project 'app/src/main/jniLibs/armeabi-v7a'
New-Item -ItemType Directory -Force -Path $nativeOutput | Out-Null
& (Join-Path $repo '.local-baseline/server19-dev/sony-arm-tools/zig-0.15.2/zig.exe') cc -target arm-linux-musleabi -shared -nostdlib -fPIC -Os -fomit-frame-pointer -fno-stack-protector (Join-Path $project 'native/paths.c') -o (Join-Path $nativeOutput 'libserver19paths.so')
if ($LASTEXITCODE -ne 0) { throw 'Private resource path bridge build failed' }
$assets = Join-Path $project 'app/src/main/assets'
New-Item -ItemType Directory -Force -Path $assets | Out-Null
Copy-Item -LiteralPath $RuntimeZip -Destination (Join-Path $assets 'runtime.zip')
& (Join-Path $tools 'gradle/gradle-8.9/bin/gradle.bat') -p $project --no-daemon --console=plain assembleDebug
if ($LASTEXITCODE -ne 0) { throw 'Android probe build failed' }
