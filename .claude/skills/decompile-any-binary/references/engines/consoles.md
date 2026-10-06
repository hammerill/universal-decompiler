# Consoles: N64, GBA, NDS, PS1, PS2, PSP, GameCube/Wii, Xbox, Xbox 360, PS3, Switch

Deliverable: a **C++/CMake PC port** with a platform layer replacing the console SDK and hardware
(`platform-layer.md`), building on Windows and Linux, loading assets that `tools/extract_assets.py` takes
from the user's own dump. The user dumps their own disc or cartridge; never download ROMs, ISOs, BIOS
or firmware. Encrypted executables are a protection: the user provides one they decrypted themselves on
their own hardware; the agent never decrypts.

## Detection signals and starting point per console
| Console | `ud scan` signals | Executable to work on | Encryption (= stop unless the user provides a decrypted one) |
|---|---|---|---|
| N64 | `.z64/.v64/.n64` magic, internal title + game code | the ROM | none |
| GBA | Nintendo logo at 0x04, `0x96` at 0xB2, title/game code | the ROM (ARMv4T, loads at 0x08000000) | none |
| NDS | logo CRC `0xCF56` at 0x15C, ARM9/ARM7 entries | the ROM (ARM9 binary + overlays) | none for retail ROM dumps |
| PS1 | `PS-X EXE`, ISO9660 + `SYSTEM.CNF` `BOOT =` | `SLUS_xxx.xx`-style PS-X EXE from the disc | none |
| PS2 | ISO9660 + `SYSTEM.CNF` `BOOT2`, ELF with R5900 flags | the boot ELF from the disc | none |
| PSP | `PSP GAME`/`PSP_GAME`, `\0PBP`, `~PSP` | `EBOOT.BIN` | `~PSP`/encrypted EBOOT |
| GameCube / Wii | disc magic (`C2339F3D` GC, `5D1C9EA3` Wii), DOL/REL | `main.dol` (+ RELs) | Wii disc partitions |
| Xbox | `XBEH`, XDVDFS `MICROSOFT*XBOX*MEDIA` | `default.xbe` (x86) | none (retail XBEs are signed, not encrypted) |
| Xbox 360 | `XEX2`, XDVDFS at 360 offsets | `default.xex` (PowerPC) | encrypted/compressed XEX |
| PS3 | `SCE\0` (SELF), ELF with OS ABI 0x66 | `EBOOT.BIN` -> decrypted `EBOOT.ELF` | SELF |
| Switch | `NSO0`, `NRO0`, `PFS0`/NSP, XCI `HEAD` | decrypted `main` NSO from ExeFS | NSP/XCI/NCA |

Disc images: extract the executable into `data/` first (7-Zip for ISO9660, `extract-xiso` for XDVDFS,
decomp-toolkit/Dolphin for GameCube images; ask before extracting large images).

## Routes
| Console | Route | Tools (`ud tools check --route ...`) |
|---|---|---|
| N64 | **static-recomp** with N64Recomp + N64ModernRuntime (+ RT64) when it fits; else clean-room with splat + Ghidra (N64LoaderWV) | `n64-recomp`, `n64` |
| GBA | clean-room: Ghidra raw import (ARM:LE:32:v4t at 0x08000000; GhidraGBA optional) | `gba` |
| NDS | clean-room: Ghidra + NTRGhidra (ARM9 + overlays) | `nds` |
| PS1 | clean-room: splat + Ghidra + ghidra_psx_ldr (PsyQ signatures name SDK functions) | `ps1` |
| PS2 | clean-room: splat + Ghidra + ghidra-emotionengine-reloaded; PS2Recomp is experimental | `ps2`, `ps2-recomp` |
| PSP | clean-room: Ghidra + ghidra-allegrex (PRX/ELF), splat optional | `psp` |
| GameCube / Wii | clean-room: decomp-toolkit (split, symbols, project) + Ghidra-GameCube-Loader | `gamecube-wii` |
| Xbox | clean-room: Ghidra + ghidra-xbe (labels XDK library functions); x86 code ports almost directly to PC | `xbox` |
| Xbox 360 | **static-recomp** with XenonRecomp (+ XenonAnalyse for function boundaries) when the title fits; else clean-room with XEXLoaderWV | `xbox360-recomp`, `xbox360` |
| PS3 | clean-room: Ghidra on the decrypted PPU ELF (PowerPC64 BE); SPU code needs separate handling | `ps3` |
| Switch | clean-room: Ghidra + Ghidra-Switch-Loader on the decrypted NSO (AArch64) | `switch` |

Search for existing decomps and recomps first (step 1): many N64, GBA, NDS, GameCube and PS1/PS2 titles
already have matching decompilations or ports.

## Platform layer specifics
Replace the SDK, not just the CPU: graphics (RSP/RDP microcode, PS2 GS/VU, GX, Xenos, RSX, NVN) behind a
renderer interface; audio (RSP audio, SPU2, AX, XMA) behind the mixer; pads -> SDL gamepads; memory
cards/saves -> files in the user's config folder; fixed console timing (NTSC/PAL frame rates) -> frame
pacing. Recompilation runtimes already provide much of this for their console.

## Required tools
Per route above. Base: Git, CMake, a C++ compiler, Python, uv; JDK + Ghidra + pyghidra-mcp for clean-room;
the console's emulator (ares/simple64, mGBA, melonDS, DuckStation, PCSX2, PPSSPP, Dolphin, xemu, Xenia
Canary, RPCS3) as the oracle, with the user's own BIOS/firmware dumps where needed.

## Deliverable shape
CMake project, `src/` per module (original addresses in comments: console virtual addresses), `src/platform/`
with the SDK replacement, `tools/extract_assets.py` reading the user's ROM/disc dump (formats documented in
it), `decomp/progress.json`, README.

## Known limits
- Self-modifying code, overlays and DMA-driven code loading need care (overlays: track per-overlay addresses).
- Hardware-timing-dependent behaviour (raster effects, cycle counting) needs emulation in the layer.
- Vector units (PS2 VU, PS3 SPU, Xbox 360 VMX128) don't map 1:1 to SSE/NEON; expect manual work.
- Byte-matching decompilation isn't the goal; use matching (objdiff) only when a playbook step needs a
  per-function check that behaviour comparison can't give.

## Verification approach
The emulator running the user's dump is the oracle: same input recording (most emulators record/replay
input), compare screenshots at fixed frames (`ud run --shot` on the port; the emulator's own screenshot), RAM
values traced in the emulator's debugger vs values logged by the port, audio by ear and by spectrogram.
