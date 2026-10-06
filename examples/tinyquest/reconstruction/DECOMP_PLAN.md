# Decompilation plan

## Target
- Binary: `data/tinyquest` (Linux build) / `data/tinyquest.exe` (Windows build), plus `data/tinyquest.pak`
- Version / edition: the CI build of `examples/tinyquest/original` (GCC 13.3, `-O1 -fno-inline`, stripped)
- Ownership: the example's original is our own code, built in CI; nothing commercial is involved
- Privacy: a real decomp repo stays private; this one is public only because the original is ours

## Done criterion (agreed at intake)
- [ ] The CMake project builds on Windows with MSVC as 64-bit (evidence pending: CI job `example` on windows-latest; no MSVC on the machine where this was written)
- [x] The CMake project builds on Linux with GCC or Clang as 64-bit
- [x] It runs with the assets extracted by `tools/extract_assets.py` from the user's copy (`data/tinyquest.pak`)
- [x] Observable state: for the same arguments it prints exactly what the original prints (every tick line,
      messages, final `result=… score=… hash=…`, the `--render` map) and returns the same exit code.
      Checked with `ud run --compare` on the default demo and on varied seeds, inputs and tick counts.

## Recon (`ud scan data/tinyquest`)
- Format / arch / bitness: ELF, x86-64, 64-bit little-endian, non-PIE (base 0x400000)
- Compiler / toolchain: GCC 13.3.0 (ELF `.comment`)
- Debug info: none (stripped)
- Engine / family: unknown native engine -> family `native`
- Protections: none found

## Prior art
`ud kb search tinyquest` / `ud kb search "TQPK"`: nothing. It's our own program, so no community work exists.

## Route and why
- Route: **clean-room** rewrite from Ghidra's output. `ud scan` also offers hybrid-dll for Windows PE
  originals; the reference build is a Linux ELF and the program is small, so a rewrite verified against
  the original's output is the shortest path.
- Tools route: `native` (`ud tools check --route native`: Git, CMake, a C++ compiler, Python, uv, JDK 21+,
  Ghidra 12.1, pyghidra-mcp)

## Module map
| Module | Address range / source | Purpose | Status |
|---|---|---|---|
| main | 0x00402122 | argument parsing, asset loading, the tick loop, final report | verified |
| world | 0x004013B5–0x0040173D, 0x00401E9B–0x0040205E | level load, player/enemy moves, bites, hash, render | verified |
| text | 0x00401D11, 0x004018E5, 0x00401E62 | rules.txt, strings.txt, message output | verified |
| pak | 0x00401396, 0x00401A4E, 0x00401BAC | TQPK archive reader (moved into tools/extract_assets.py) | verified |
| platform | 0x00401815 | whole-file read (replaced by platform::read_file) | verified |
| crt, imports | 0x00401000–0x00401390, 0x004025C0 | GCC/glibc startup, PLT thunks | skipped |

## Third-party libraries identified
| Library | Version | Evidence | Plan |
|---|---|---|---|
| glibc | 2.38+ (`__isoc23_*` symbols) | dynamic imports | use the platform's C/C++ runtime |

## Middleware replacement plan
| Original | Replacement | Notes |
|---|---|---|
| TQPK archive reader (in the exe) | `tools/extract_assets.py` + loose files in `data/assets/` | the program reads extracted files; the archive format is documented in the script |

## Platform layer
- Backend: C stdio only (`src/platform/platform_stdio.cpp`). The original never opens a window, reads input
  devices or plays audio, so there is no SDL backend; a program that does gets the SDL3 backend from
  `ud init --scaffold`.
- APIs replaced: `fopen`/`fread` whole-file reads -> `platform::read_file`.

## Target layout
```
CMakeLists.txt
src/main.cpp              0x00402122
src/game/world.{h,cpp}    level, simulation, hash, render
src/game/text.cpp         rules, strings, messages
src/platform/             read_file, asset paths
tools/extract_assets.py   TQPK -> data/assets/
decomp/progress.json      ud funcs
```
