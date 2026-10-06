# DECOMPLOG

The journal of this decompilation. Anything that isn't written here is lost at the next context compaction.

## Status
- Phase: verify (Linux done; Windows evidence comes from CI)
- Done criterion: met on Linux; the Windows item waits for the CI job `example`
- Next step: none; field note written as `knowledge/tooling/ghidra-headless-export-and-decompile.md` (tooling,
  since the subject is our own example program)
- Circuit breaker: never tripped

## Facts
| What | Value | Source |
|---|---|---|
| Binary | data/tinyquest, 18,736 bytes, ELF x86-64, non-PIE, stripped | ud scan |
| Compiler | GCC 13.3.0 (Ubuntu 13.3.0-6ubuntu2~24.04.1) | ELF .comment |
| Functions | 68 in Ghidra: 25 real, 43 thunks; 17 are game code, 8 CRT | ud funcs stats |
| Global state | one `World` at 0x004080E0 (0x300 bytes), archive state at 0x004083E0 | main's references |
| Assets | tinyquest.pak: TQPK v1, 3 entries (level1.map, rules.txt, strings.txt) | pak_open/pak_extract |
| Direction tables | dy {-1,0,1,0} at 0x00403170, dx {0,1,0,-1} at 0x00403180 | read from .rodata bytes |

## Log
### 2026-10-06
- Intake: the user's copy is `data/tinyquest` + `data/tinyquest.pak`. Done criterion agreed: identical stdout
  and exit code for the same arguments, builds on MSVC x64 and GCC x86-64, runs from extracted assets.
- `ud init`, `ud scan data/tinyquest`: ELF x86-64, GCC 13.3, stripped, no protection, family native;
  routes: clean-room (hybrid-dll is only offered for Windows PE originals).
- `ud kb search tinyquest`: nothing. No prior art (our own program).
- `ud tools check --route native`: all present (Ghidra 12.1.4, JDK 25, pyghidra-mcp 0.2.7).
- Ghidra headless: `analyzeHeadless ghidra tinyquest -import data/tinyquest -scriptPath <ud>/ud/ghidra
  -postScript ExportFunctions.java build/functions.json -postScript DecompileAll.java build/decomp`
  (9 s). 68 functions exported, 25 decompiled into build/decomp (gitignored, never committed).
- `ud funcs import build/functions.json`: 68 entries, 43 thunks auto-skipped.
- main = 0x00402122 (the only caller of the archive functions; it holds the "%s/tinyquest.pak" format and
  the tick-line printf). Its callees give the module split: 0x401BAC opens the archive, 0x401A4E extracts
  by name (called with "level1.map", "rules.txt", "strings.txt"), 0x401D11 parses rules into the struct at
  World+0x2EC, 0x4018E5 parses strings into 0x30-byte slots at World+0x168, 0x4013D3 loads the level,
  0x40200C is the per-tick update, 0x40173D the final hash, 0x40205E the `--render` map.
- World layout from field accesses: tiles 11 rows x 0x15 bytes at +0; px/py +0xE8/+0xEC; hp +0xF0; score
  +0xF4; coins_left +0xF8; enemies (12 bytes: x, y, alive) from +0xFC; enemy_count +0x15C; rng +0x160;
  outcome +0x164; string_count +0x2E8; rules +0x2EC (hp, coin_score, exit_bonus, enemy_damage,
  chase_radius, with defaults 3/1/0/1/3 set before parsing).
- Archive format from 0x401BAC/0x401A4E: "TQPK" magic (memcmp with a 4-byte constant), u16 version must be
  1, u16 count <= 16, 40-byte entries (24-byte name, u32 offset, stored size, real size, flags byte at +36);
  flags bit 0 = RLE in (count, byte) pairs, output capped at the real size; extraction refuses entries whose
  real size >= the 4096-byte buffer.
- 0x4013B5 is the ANSI C LCG (x*1103515245+12345, return bits 16..30) on World+0x160.
- 0x401518 (enemies) is the hardest read: the optimiser turned the chase rule into a goto web. Read it
  as: Manhattan distance <= chase_radius -> step along x if |dx| >= |dy| and x is free, else along y if
  free, else along x if free; otherwise draw rng % 4 and step using the two tables unless the target is a
  wall or the exit tile. Only wanderers consume the rng, so the order of enemies matters.
- The program is small, so all modules were ported in one pass instead of a staged vertical slice (on a
  real target: main + asset loading first, then one module at a time). `tools/extract_assets.py`
  reimplements the archive reader; the program reads data/assets/* through platform::read_file (replaces
  0x401815). First `ud build` failed: `world.cpp:161: deducing from brace-enclosed initializer list
  requires #include <initializer_list>` (GCC). Fixed; second build OK.
- `uv run tools/extract_assets.py data` -> 3 files; `ud assets check` OK.

## Done check (evidence)
- `ud run --compare --timeout 20` on: default demo (exit reached, result=1 score=90 hash=c99dca6c),
  `--seed 1`, `--seed 42 --render`, `--inputs RRRRDDLLUU --ticks 25`, `--seed 99 --ticks 200 --render`,
  `--inputs .`, `--seed 4000000000 --ticks 120`: **MATCH** every time (identical stdout, same exit code).
- Linux GCC 13.3 x86-64 build: `ud build` OK, comparisons above.
- Windows MSVC x64: the CI job `example` (`.github/workflows/test.yml`) builds the original and the
  reconstruction on windows-latest and runs the same comparisons. It had not run yet when this entry was
  written; its result is the evidence for that item.
- `ud funcs stats`: 17/17 game functions verified, CRT and thunks skipped.

## Known gaps
- Error paths differ in wording: the original reports archive problems ("cannot open data/tinyquest.pak",
  "damaged archive"); the reconstruction reads extracted files and reports a missing file instead. Exit
  codes for those paths are kept (10 missing, 12 bad level).
