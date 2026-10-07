---
kind: title
title: Clean-room C++ reconstruction of Zuma Deluxe 1.0.0.1 on SDL3
subject: Zuma Deluxe
subject_version: '1.0.0.1, MSN/Zone partner build (Dec 2003), ZumaDeluxe.exe 1,290,240 bytes, sha256 823d573e68cdc49f...'
platform: windows
family: native
engine: unknown
route: clean-room
formats:
- PE32 x86 32-bit
compiler: Microsoft Visual C++ Visual Studio .NET 2002 (7.0) [build 9466]
tools:
- Ghidra 12.1.4 (headless + pyghidra-mcp)
- ud 0.1.0
- GCC 13.3 (Linux x86-64)
- MinGW-w64 GCC 13 posix (Windows x64 cross)
- Apple Clang (macOS arm64)
- CMake 3.28
- SDL 3.4.18
- libopenmpt
- Tremor (xiph, 2025-04-02)
status: working
agents:
- Claude Code (Opus 5.5)
humans: []
date: '2026-10-07'
links:
- https://github.com/alula/CircleShootApp
tags:
- popcap
- sexyapp
- bass
- mo3
- vorbis
- audio
- savegame
---
# Clean-room C++ reconstruction of Zuma Deluxe 1.0.0.1 on SDL3

> A C++17/CMake reconstruction of Zuma Deluxe (PopCap's SexyApp framework, 2003) that builds 64-bit for Linux,
> Windows and macOS on SDL3. Every game function was rewritten against the binary, using a public decomp of a
> different build only as a map. It runs from the loading screen through the menus and adventure map, and
> Adventure 1-1 and 1-2 play to completion (driven by an autoplay aid). It loads saved games written by the
> original, and all 38 sound effects decode bit-identical to what the original played.

## Setup
- Original: the MSN/Zone partner build 1.0.0.1, PE32 MSVC 7.0 (VS.NET 2002), static CRT, full RTTI, no PDB.
  Game files are loose (images, fonts, levels, sounds, music, properties); audio went through BASS (bass.dll).
- Ghidra 12.1.4 headless decompile-all (per-function C dumped locally, never committed) plus pyghidra-mcp for
  interactive work. The reconstruction was built and run on Ubuntu 24.04 under WSL2 (WSLg).
- Dependencies via CMake FetchContent: SDL3, stb (images), libopenmpt (MO3 music), libogg + Tremor (OGG).

## Route and why
`ud scan`: native PE32, MSVC 7, RTTI. Prior art: alula/CircleShootApp is a full decomp of the PopCap.com build;
the PopCap Framework 1.3 source is public. The user chose an independent reconstruction on a portable SexyApp
layer instead of the DLL-injection hybrid, so it runs natively on 64-bit Linux. The reference decomp is a
structural map only: partner builds differ in many small ways, so every function was checked against this
binary.

## What the program really does
- The 2003 SexyApp framework sits in the second half of .text, the game in the first (~1300 functions), roughly
  in link order: Ball, Gun, SpriteMgr, CurveMgr, Board, ProfileMgr, LevelParser, TransitionMgr, the screens and
  dialogs, CircleShootApp. RTTI vtables give every class name and its overrides; diffing a class's vtable
  against its base finds the overrides quickly.
- Framework 1.3 is close to the 2003 one. The differences that matter: the dialog button ids (below), virtual
  slot order, and 1.22's opt-in software triangle rasterisers.
- Three RNGs: an app MT RNG and a loading-thread MT RNG (both seeded from the framework's Sexy::Rand), plus
  MSVC's CRT rand() (LCG 214013/2531011) for the star field, background transitions and game-over tips.
  Reproduce the CRT LCG if sequences must match.
- Game time is 100 updates/s; board time = state count × 10 ms (it stops while paused).
- Saves: userdata/users.dat, userN.dat, highscores.dat, adv/prc<N>.sav; save-game version 5. All are written
  through a symmetric DataSync (one function serialises both ways), so get each SyncState field order and
  width from the binary: several are ushort or byte where you'd expect int.
- Resource IDs are in resources.xml file order; a table in .data maps each ID to its global pointer.
- partner.xml (signature-checked in the original) sets ProdName, Title, DefaultWindowed and a MoreGamesLink:
  with a link, "More Games" opens a URL instead of the in-game screen.

## Build and run
`cmake -S . -B build/rel -DCMAKE_BUILD_TYPE=Release && cmake --build build/rel -j`. A MinGW-w64 toolchain file
cross-builds a static, self-contained zuma.exe that runs on Windows. On macOS (Xcode Command Line Tools +
CMake) the same command line builds a native arm64 binary after two Clang fixes (see the tooling note on
macOS); saves go to ~/Library/Application Support/PopCap/Zuma/. tools/extract_assets.py copies the six
asset folders from the user's install and checks them against resources.xml and levels.xml. The program finds
the game folder itself (cwd, ./data, next to the exe).

## Verification
- Oracle 1: the original's own save files. A mid-game adv1.sav written by the original loads and continues;
  the "continue?" dialog shows the right level, name and score.
- Oracle 2: the original's sounds/cached_*.wav (BASS's decoded output): all 38 OGGs decode to identical samples.
- Env-gated aids in the framework: periodic PNG screenshots, scripted input at given update counts, a timed exit,
  a watchdog that dumps every thread's stack on a stall (SIGUSR2 + backtrace, no gdb needed) and an autoplayer.
  Together they drove menu → map → 1-1 → 1-2 unattended, under AddressSanitizer.
- NOT verified: the MSVC build; frame-by-frame comparison with the original (no side-by-side run yet); gauntlet
  mode, the credits and the later temples only partly.

## Gotchas
1. **Ghidra truncates ~1150 functions after their first free().** Cause: the "Non-Returning Functions -
   Discovered" analyzer marks this binary's CRT free() as noreturn. Fix: disable that analyzer in a headless
   pre-script before auto-analysis, then re-export.
2. **Dialog Yes/No buttons do nothing.** Cause: 1.3 numbers dialog buttons 1000/1001 and maps them in
   SexyAppBase; the 2003 framework numbers them dialogId+2000 / +3000 and passes that id straight to the
   app's ButtonDepress, which the game switches on. Fix: use the 2003 numbering in Dialog.
3. **Rotated and stretched images draw nothing (debug: assert "You need to call SWTri_AddDrawTriFunc").**
   Cause: since 1.22 the software triangle rasterisers are opt-in. Fix: call SWTri_AddAllDrawTriFuncs() at init.
4. **Crashes found only by AddressSanitizer in the vendored 1.3 code:** DescParser erases begin() of an empty
   string; SlowStretchBlt reads one pixel past the source when upscaling (its right-neighbour sample at the last
   column); PolyFill frees new[] memory with delete; vformat reuses a consumed va_list when it retries with a
   bigger buffer (garbles strings over 160 chars on x86-64). MSVC 2003 tolerated all of these.
5. **Game hangs at loading under X11.** Cause: a resource error opens a message box from the loading thread,
   and Xlib deadlocks with the main loop. Fix: queue off-thread message boxes for the main loop.
6. **"Failed to load sound" for 11 sounds.** Cause: they are Vorbis floor-0 streams, which stb_vorbis rejects.
   Fix: decode with Tremor, which also matches BASS's output exactly (see the tooling note on BASS-era OGG).
7. **Cached WAVs from the original fail to parse.** Cause: BASS wrote a "dep " chunk (source name + FILETIME)
   of odd size without the RIFF pad byte. Fix: skip that chunk unpadded before handing the file to a WAV reader.
8. **Copying the install's userdata/ silently copied nothing.** Cause: std::filesystem::copy on a directory with
   only skip_existing copies nothing (recursive or default options are required). Fix: recursive | skip_existing.
9. **Reconstructed SyncState orders that "look right" break original saves.** Cause: guessed widths. Fix: take
   each Write/Read call and its width from the binary; the original's saves are the test.

## Open questions
- Build with MSVC on Windows and compare screens side by side with the original.
- Gauntlet, credits and the later temples need the same scripted verification.
