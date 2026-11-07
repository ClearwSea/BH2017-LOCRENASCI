"""Rebuild the optional Windows audio tool. Copyright (c) 2026 ClearwSea; MIT."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess

p = argparse.ArgumentParser()
p.add_argument('--source', required=True, type=Path)
p.add_argument('--build', required=True, type=Path)
p.add_argument('--zig', required=True, type=Path)
a = p.parse_args()
source, build, zig = a.source.resolve(), a.build.resolve(), a.zig.resolve()
for tool in ('cmake', 'ninja', 'sh'):
    if not shutil.which(tool):
        p.error(tool + ' must be on PATH')
build.mkdir(parents=True, exist_ok=True)
wrappers = build / 'compiler'
wrappers.mkdir(exist_ok=True)
for name, command in [('ar', 'ar'), ('ranlib', 'ranlib'), ('dlltool', 'dlltool -m i386:x86-64')]:
    (wrappers / (name + '.cmd')).write_text('@echo off\r\n"' + str(zig) + '" ' + command + ' %*\r\n')
toolchain = build / 'zig-windows.cmake'
toolchain.write_text('\n'.join([
    'set(CMAKE_SYSTEM_NAME Windows)',
    'set(CMAKE_SYSTEM_PROCESSOR x86_64)',
    'set(CMAKE_C_COMPILER "' + zig.as_posix() + '")',
    'set(CMAKE_C_COMPILER_ARG1 "cc -target x86_64-windows-gnu")',
    'set(CMAKE_CXX_COMPILER "' + zig.as_posix() + '")',
    'set(CMAKE_CXX_COMPILER_ARG1 "c++ -target x86_64-windows-gnu")',
    'set(CMAKE_AR "' + (wrappers / 'ar.cmd').as_posix() + '")',
    'set(CMAKE_RANLIB "' + (wrappers / 'ranlib.cmd').as_posix() + '")',
]) + '\n')
env = dict(os.environ, SOURCE_DATE_EPOCH='1791590400')
flags = '-ffile-prefix-map=' + source.as_posix() + '=vgmstream-source -Wno-error=date-time'
subprocess.run(['cmake', '-S', str(source), '-B', str(build), '-G', 'Ninja',
    '-DCMAKE_TOOLCHAIN_FILE=' + str(toolchain), '-DCMAKE_BUILD_TYPE=Release',
    '-DCMAKE_POLICY_VERSION_MINIMUM=3.5', '-DCMAKE_C_FLAGS=' + flags,
    '-DCMAKE_CXX_FLAGS=' + flags, '-DDLLTOOL=' + str(wrappers / 'dlltool.cmd'),
    '-DUSE_FFMPEG=OFF', '-DUSE_G719=OFF', '-DUSE_G7221=OFF',
    '-DBUILD_FB2K=OFF', '-DBUILD_WINAMP=OFF', '-DBUILD_XMPLAY=OFF',
    '-DVGMSTREAM_VERSION=r2117-312-g7c520e8f-bh2017'], check=True, env=env)
# Some CMake/Zig combinations infer zig.exe as the archiver without its subcommand.
rules = build / 'CMakeFiles/rules.ninja'
text = rules.read_text()
text = text.replace('zig.exe qc ', 'zig.exe ar qc ')
rules.write_text(text)
subprocess.run(['cmake', '--build', str(build), '--parallel', '6'], check=True, env=env)
