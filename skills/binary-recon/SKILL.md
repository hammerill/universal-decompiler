---
name: binary-recon
description: Work out what a binary is before decompiling it - prior art, container format, architecture and bitness, compiler and toolchain (MSVC version from the Rich header, GCC/Clang, Metrowerks, SN Systems), debug info (PDB path, DWARF, symbols), linked middleware (RenderWare, Bink, FMOD, Wwise, Havok, PhysX, Scaleform, Lua), engine, packers/DRM/anti-cheat - and choose the route. Use at the start of any decompilation or when the user asks "what is this exe/ROM", "what engine/compiler built this", "can this be decompiled", "is it protected". Produces DECOMP_PLAN.md.
---

# Binary recon

Goal: in a few minutes, know exactly what you're dealing with, whether you may proceed, and which route
to take. Write it down in `DECOMP_PLAN.md` so every later step relies on it.

## 0. Prior art
- `ud kb search "<title>"`, `ud kb search "<engine>"`, `ud kb search "<format or middleware>"`.
- Search the web as it is now: "<title> decompilation", "<title> decomp", "<title> source port",
  "<title> recomp", "<title> reverse engineering", "<engine> file formats". Check GitHub and the title's
  modding wiki.
- A complete working decompilation of the same version -> stop and tell the user. Partial work, symbol maps,
  format documentation -> log it as reference.

## 1. Scan
```bash
ud scan data/<binary>          # one file (its folder is used as context)
ud scan data/                  # an install: picks the main executable(s)
ud scan data/<binary> --json   # for your own parsing
```
It reports, each with a confidence:
- **format**: PE/COFF, ELF, Mach-O, XBE, XEX, SELF, DOL/REL, NSO/NRO/NSP, PS-X EXE, N64/GBA/NDS ROMs,
  GameCube/Wii/PS1/PS2/PSP/Xbox disc images, .NET assemblies, JARs, archives, installers;
- **architecture**, bitness, endianness, platform;
- **compiler**: Rich header -> Visual Studio version; ELF `.comment`; strings for MinGW, Metrowerks,
  SN Systems ProDG, Borland/Delphi, Watcom, Go, Rust, Nuitka;
- **debug info**: PDB path (the file itself is almost never available: don't hunt for it), DWARF, symbol
  tables, .NET metadata;
- **middleware** with an open replacement suggestion;
- **engine/family**, other signals, **protections**;
- **ranked routes** with the tools each needs and the playbook to read.

Read the playbook: `skills/decompile-any-binary/references/engines/<family>.md`.

## 2. Check by hand what a scan can't see
- Several executables (launcher + game, 32 and 64-bit builds): scan each; pick the one that contains the
  game logic (largest, most imports from graphics/audio APIs, most game strings).
- Strings tell you a lot: `strings -n 6 data/<binary> | less` (or Ghidra's string search): asset names, log
  formats, source file paths left by asserts (`c:\dev\game\src\render\...` gives you the module map), build
  dates, middleware versions.
- Imports by DLL: the platform-layer work ahead (D3D9 vs D3D11, DirectInput vs XInput, DirectSound...).
- Version: file properties, a version string, the store build ID. Write the exact one down.

## 3. Decide
- **Protected?** (DRM, packer, anti-cheat, obfuscator, encrypted executable): stop and tell the user (see
  `skills/decompile-any-binary/references/safety.md`). Suggest an unprotected edition they may own.
- **Route**: hybrid-dll / clean-room / static-recomp / managed-decompile / engine-project / script-recovery
  (the main skill's step 4). The cheapest route that reaches the done criterion wins.
- **Tools**: `ud tools check --route <route>`; missing -> stop with the printed install steps.

## 4. Write DECOMP_PLAN.md
Fill in the template `ud init` created: Target (exact version, ownership, privacy reminder), Done criterion,
Recon (the scan's findings), Prior art, Route and why, Module map (first guess from strings/imports),
Third-party libraries, Middleware replacement plan, Platform layer, Target layout. Then continue with the
main loop (inventory, vertical slice).
