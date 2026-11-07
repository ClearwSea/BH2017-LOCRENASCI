#!/usr/bin/env bash
# Copyright (c) 2026 ClearwSea; MIT, see ../../LICENSE.
set -euo pipefail
src=$(cd "${1:?usage: rebuild_ffmpeg.sh /path/to/ffmpeg-9.0.2}" && pwd)
: "${ZIG_EXE:?set ZIG_EXE to Zig 0.15.2 zig.exe}"
zig=$(cygpath -m "$ZIG_EXE")
wrapper="$src/.bh2017-compiler"
mkdir -p "$wrapper"
for entry in zigcc zigar zigranlib; do
    case "$entry" in
        zigcc) args='cc -target x86_64-windows-gnu';;
        zigar) args='ar';;
        zigranlib) args='ranlib';;
    esac
    printf '#!/bin/sh\nexec "%s" %s "$@"\n' "$zig" "$args" > "$wrapper/$entry"
done
# Avoid embedding the local source directory in assertion messages.
printf '#!/bin/sh\nexec "%s" cc -target x86_64-windows-gnu "-ffile-prefix-map=%s=ffmpeg-source" "-ffile-prefix-map=%s=ffmpeg-source" "$@"\n' "$zig" "$src" "$(cygpath -m "$src")" > "$wrapper/zigcc"
chmod +x "$wrapper/"*
export PATH="$wrapper:$PATH"
cd "$src"
./configure --target-os=mingw64 --arch=x86_64 --enable-cross-compile \
 --disable-everything --enable-ffmpeg --disable-ffprobe --disable-ffplay \
 --disable-gpl --disable-nonfree --disable-autodetect --disable-network \
 --disable-doc --enable-debug=0 --disable-x86asm --disable-inline-asm \
 --disable-stripping --enable-small --enable-protocol=file \
 --enable-demuxer=usm --enable-muxer=mp4 \
 --enable-decoder=hca,aac,pcm_s16le,h264 --enable-encoder=aac \
 --enable-parser=h264,aac --enable-bsf=extract_extradata,aac_adtstoasc \
 --enable-filter=anull,aformat,aresample --cc=zigcc --host-cc=zigcc \
 --ar=zigar --ranlib=zigranlib
make -j"${JOBS:-6}" ffmpeg.exe
