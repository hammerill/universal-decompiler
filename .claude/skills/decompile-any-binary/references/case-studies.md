# Case studies

What the big reconstructions did, so the agent can pick a route by precedent. Versions and project states
move: check the current repositories before relying on any detail.

## re3 / reVC (GTA III, Vice City): the hybrid route
- **Route:** re3-style hybrid. The project started as a DLL injected into the original executable; functions
  were reimplemented one at a time and swapped in, so the game stayed playable after every change and
  every reimplemented function was tested in the real game. Once enough was replaced the result became a
  standalone executable that runs on many platforms.
- **Middleware:** the RenderWare engine was replaced by librw, an open-source reimplementation of the
  RenderWare API written by one of the developers. That's the model for proprietary middleware: an open
  equivalent with the same API, so the game code doesn't change.
- **Assets:** none shipped; the user's own game folder is required.
- **Lesson:** the hybrid gives you a permanent oracle (the rest of the original runs around your function).
- **Legal:** see `safety.md`: taken down and sued despite shipping no assets.

## OpenRCT2 (RollerCoaster Tycoon 2)
- Started in April 2014 by patching the original `rct2.exe` so it loaded `openrct2.dll` and called its
  WinMain first; the DLL called back into the original for every function not yet reimplemented.
- Functions were replaced bit by bit until, in October 2015, the game no longer needed the original code
  (graphics, sounds and objects still come from the user's RCT2 install). Then it was ported to other
  systems and extended.
- **Lesson:** the hybrid route scales to a whole game; plan the switch from "DLL in the original" to
  "standalone executable" as an explicit milestone.

## Super Mario 64: decompilation, then a PC port
- A matching decompilation (C that compiles back to the identical ROM) came first; the PC port replaced the
  N64 graphics and audio layers on top of it.
- The build extracts assets from the user's own ROM with an `extract_assets.py` script: the model for
  `tools/extract_assets.py` here.
- **Lesson:** byte-matching is a verification method, not the goal; here the goal is a PC reconstruction,
  so behaviour matching against the original is enough unless a playbook needs more.

## Zelda64Recomp (Majora's Mask): static recompilation
- Built with N64Recomp: the game's MIPS code is translated into C automatically, linked against
  N64ModernRuntime (the N64 environment) and the RT64 renderer. It runs natively, not emulated, and needs
  the user's own ROM.
- **Lesson:** when a mature recompiler exists, recompilation gets a running native build in days; the
  remaining work is the runtime/platform layer and fixes for the parts recompilation can't handle.

## Unleashed Recompiled (Sonic Unleashed, Xbox 360)
- A static recompilation of the Xbox 360 game with XenonRecomp (PowerPC code to C++) and XenosRecomp
  (shaders to HLSL), released in 2025 for Windows and Linux. No game assets included: the user provides
  files from their own copy.
- **Lesson:** Xbox 360 titles can go the recompilation route; most of the effort moves into reimplementing
  the console's graphics and system libraries behind a PC backend.

## DevilutionX (Diablo)
- Devilution reconstructed Diablo's source from the original binary; DevilutionX ports that to modern
  systems with SDL and needs the user's own `DIABDAT.MPQ`.
- **Lesson:** the reconstruction first, the port second; an SDL platform layer makes the port mostly about
  replacing Win32/DirectDraw/DirectSound calls.

## TinyQuest (this repo's worked example)
- `examples/tinyquest/`: a small stripped ELF reversed with Ghidra 12.1.4 headless, tracked with `ud funcs`,
  rebuilt as C++17/CMake and verified with `ud run --compare` on seven argument sets. Its custom archive
  format was worked out from the binary and reimplemented in `tools/extract_assets.py`.
- **Lesson:** the full loop, small enough to read in one sitting. Its `DECOMPLOG.md` shows the level of
  detail a journal needs (addresses, struct offsets, what each function does, every failure).
