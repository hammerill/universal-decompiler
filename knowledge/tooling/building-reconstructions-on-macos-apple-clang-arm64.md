---
kind: topic
title: Building reconstructions on macOS (Apple Clang, arm64)
family: tooling
status: working
tools:
- Apple Clang 21 (Xcode Command Line Tools)
- CMake 4.1
- SDL 3.4.18
- ud 0.1.0
agents:
- Claude Code (Opus 5.5)
humans: []
date: '2026-10-07'
links: []
tags:
- macos
- arm64
- clang
- portability
- cmake
---
# Building reconstructions on macOS (Apple Clang, arm64)

> A reconstruction that builds with GCC on Linux usually builds on macOS (Apple silicon) with the same CMake
> command line after a handful of small source fixes. Most of them are things GCC only warns about but Clang
> rejects. Seen when the Zuma Deluxe reconstruction (SexyApp framework and game code) moved from GCC 13 on
> Linux to Apple Clang on an arm64 Mac, and checked with TinyQuest and the SDL3 scaffold.

## When to use it
When macOS is one of the targets, or when a reconstruction written against GCC on Linux is built on a Mac
for the first time. Build on macOS (or with Clang anywhere) early: the fixes are trivial one at a time and
tedious in bulk.

## How
- Toolchain: `xcode-select --install` (Apple Clang, libc++, git) and CMake (`brew install cmake`). The Linux
  command line works unchanged: `cmake -S . -B build/mac -DCMAKE_BUILD_TYPE=Release` then
  `cmake --build build/mac -j`. `ud build` does the same.
- Dependencies fetched by CMake (SDL3, stb, libopenmpt, libogg, Tremor) built with no extra packages. SDL3
  picks Cocoa, Metal and CoreAudio by itself, unlike Linux, where it needs the X11/Wayland/audio dev
  packages.
- The build is native arm64. `-DCMAKE_OSX_ARCHITECTURES="arm64;x86_64"` gives a universal binary; Rosetta 2
  runs an x86-64 build if a difference might come from the architecture.
- Per-user data: `SDL_GetPrefPath` returns `~/Library/Application Support/<org>/<app>/`. The Zuma build keeps
  profiles, saves and the former registry settings there (Linux: `~/.local/share/...`, Windows: `%APPDATA%`).
- Verification: TinyQuest's end-to-end check (`examples/tinyquest/run_example.py`) gives 7/7 identical
  outputs with Apple Clang 21 on arm64, and `ud init --scaffold` + `ud build` + a headless run pass.

## Gotchas
1. **`ISO C++17 does not allow 'register' storage class specifier` stops the build.** Cause: framework code
   from 2003 (a CRC table loop) used `register`; GCC only warns, Clang makes it an error in C++17. Fix:
   delete the keyword. It never changed code generation.
2. **`non-constant-expression cannot be narrowed from type 'int' to 'float' in initializer list`.** Cause:
   brace initialisers fed non-constant values of a wider or different type (`float px[4] = { 0, rect.mWidth,
   ... }` with `int` fields; `char s[2] = { code - 0x80, 0 }`). GCC warns (`-Wnarrowing`), Clang errors
   (`-Wc++11-narrowing`). Fix: an explicit cast around the whole expression, `(char)(code - 0x80)` and
   `(float)rect.mWidth`, so the value is exactly what the original computed.
3. **Linker warnings `-s is obsolete` and `argument unused during compilation: '-no-pie'`** (TinyQuest's
   "original", built stripped and non-PIE to look like a shipped binary). Cause: macOS executables are
   always PIE and Apple's linker dropped `-s`. Fix: an `elseif(APPLE)` branch in CMake with
   `-Wl,-x` (removes local symbols) and no `-no-pie`; addresses then differ between runs, so compare
   behaviour, not pointers.
4. **Things to expect in other code bases** (not hit by Zuma, but common in GCC-only code): `<malloc.h>`,
   `<endian.h>` and `fopen64` don't exist; `sem_init` fails; x86 intrinsics and inline assembly don't
   compile on arm64; Clang fuses `a * b + c` into multiply-add on arm64, which changes float results in the
   last bits (`-ffp-contract=off` when the oracle compares floats). Details in
   `skills/decompile-any-binary/references/cpp-port.md`, section "macOS".

## Seen in
- [Zuma Deluxe 1.0.0.1 on SDL3](../zuma-deluxe/clean-room-c-reconstruction-of-zuma-deluxe-1-0-0-1-on-sdl3.md)
