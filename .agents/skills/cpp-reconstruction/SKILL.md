---
name: cpp-reconstruction
description: Turn decompiler output into buildable, behaviour-faithful C++17 with CMake that compiles with MSVC on Windows, GCC/Clang on Linux and Apple Clang on macOS as 64-bit - project layout, original-address comments, structs from offsets, the platform layer (SDL3) replacing Win32/DirectX/console SDKs, replacing proprietary middleware with open equivalents (librw-style), the re3-style DLL-injection hybrid, 32-to-64-bit porting pitfalls, and the macOS/arm64 fixes (Clang strictness, missing glibc headers, x86 intrinsics). Use when writing or fixing the reconstruction's code, setting up its CMake build, or porting it off the original platform.
---

# C++ reconstruction

Conventions in detail: `skills/decompile-any-binary/references/cpp-port.md`. Platform APIs:
`skills/decompile-any-binary/references/platform-layer.md`. Worked example:
`examples/tinyquest/reconstruction/`.

## Start
- `ud init --scaffold` writes a CMake (>= 3.20, C++17) skeleton: `src/main.cpp`, `src/platform/` with an
  SDL3 backend (fetched by CMake when it isn't installed) and a headless null backend, warnings on, output
  in `build/bin/`, and a `tools/extract_assets.py` template. Rename the target (`-DUD_TARGET=<name>` or edit
  `CMakeLists.txt`) and set `[run] exe` in `ud.toml`.
- `ud build` configures and builds (64-bit by default with MSVC), keeps the full log in
  `build/ud-build.log`, and prints the first errors as `file:line: message`. Fix the first error, rebuild.

## Porting a function
1. Decompile it (pyghidra-mcp `decompile_function`) after naming and typing it in Ghidra; port the cleaned-up
   version, not the raw one.
2. Put it in the module's file with its address:
   ```cpp
   // 0x00401518  move_enemies
   void move_enemies(World& w) { ... }
   ```
3. Translate idioms (table in `cpp-port.md`): struct fields for offsets, `bool` for `~x >> 31` tricks,
   `if/else` for `goto` webs (then test the conditions), library calls for inlined `memcpy`/`strlen`.
4. Keep observable behaviour identical: iteration order, RNG call order, integer widths and signedness,
   float order of operations, side-effect order. Don't fix bugs silently.
5. Build, then mark it: `ud funcs set <addr> --status ported`; after it passes the oracle, `verified`.

## Structure
- One folder per module (from `DECOMP_PLAN.md`'s module map); headers declare the recovered structs with
  their original offsets in comments.
- Globals of the original become members of a few explicit state objects (or stay globals at first; refactor
  once verified).
- No direct OS/console calls outside `src/platform/`.

## Middleware
For each row of `DECOMP_PLAN.md`'s middleware table: an open equivalent with the same API where one exists
(librw for RenderWare, as re3 did), a reimplementation of the used subset, or a stub for things that don't
matter offline (online services, telemetry, launchers). `ud scan` suggests replacements. Fetch open
libraries with CMake `FetchContent` pinned to a tag, or vcpkg; never commit their binaries.

## The hybrid route
While the original still runs the show: a `SHARED` target for the original's architecture
(`ud build -D CMAKE_GENERATOR_PLATFORM=Win32` on MSVC for 32-bit originals), a proxy-DLL or import-table
loader on a **copy** of the executable in `data/`, detours (MinHook/SafetyHook) at the original addresses,
and a table to switch each replacement off for bisecting. Then the standalone 64-bit target. Details in
`cpp-port.md`.

## Portability checklist before calling it done
- Builds from a clean `build/` with MSVC x64, with GCC or Clang on x86-64 Linux and with Apple Clang on macOS
  arm64, no warnings you didn't look at.
- No `long` in file formats, no pointers in 32-bit fields, `wchar_t` handled, case-insensitive asset lookup on
  Linux and macOS, paths with `/`, per-user files under the platform's own folder (`SDL_GetPrefPath`).
- No `register`, no narrowing inside braces, no glibc-only headers, no x86 intrinsics or inline assembly
  without a portable path (`cpp-port.md`, "macOS").
- On macOS the default output is a bare executable; a `.app` bundle is an extra `app` target added only when
  the user asks for one (`cpp-port.md`, "App bundle").
- The null/headless backend still builds (oracle runs depend on it).
