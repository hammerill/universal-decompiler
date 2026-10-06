---
kind: topic
title: "Ghidra headless: export the function list and decompile everything for ud"
family: tooling
tags: [ghidra, headless, analyzeHeadless, ud-funcs]
tools: ["Ghidra 12.1.4", "JDK 25 (Temurin)", "ud 0.1.0"]
status: working
agents: ["Claude Code (Opus 5.5)"]
humans: []
date: 2026-10-06
links: []
---

# Ghidra headless: export the function list and decompile everything for ud

> `analyzeHeadless` with the two Java scripts that ship in `ud/ghidra/` imports and analyses a binary, writes
> the function list that `ud funcs import` reads, and writes the decompiler's C per function into the
> gitignored `build/`. It's the no-MCP path, and the fastest way to seed the tracker.

## When to use it
- Seeding `decomp/progress.json` (sizes included, unlike the MCP symbol search).
- Agents without MCP, CI, or batch work on many binaries.

## How
```bash
"$GHIDRA_INSTALL_DIR/support/analyzeHeadless" ghidra <project> -import data/<binary> \
  -scriptPath "<universal-decompiler>/ud/ghidra" \
  -postScript ExportFunctions.java build/functions.json \
  -postScript DecompileAll.java build/decomp
ud funcs import build/functions.json
```
Re-run on the already analysed program with `-process <binary> -noanalysis` instead of `-import`. On
Windows: `analyzeHeadless.bat`. Java GhidraScripts work in headless mode without any Python setup.

## Gotchas
1. **More "functions" than the program has.** **Cause:** Ghidra lists PLT stubs and a synthetic EXTERNAL
   block (for a small non-PIE ELF: 20 PLT thunks plus 22 EXTERNAL entries at a fake address range above the
   real sections) besides the real code. **Fix:** `ud funcs import` marks thunks skipped; assign the rest
   with `ud funcs set --range <start>-<end> --module imports`.
2. **Compiler runtime shows up as unnamed functions.** **Cause:** GCC/glibc startup (`_start`, tm-clone
   registration, global dtors) is real code in the binary. **Fix:** identify it once (it sits around the
   entry point and `.init`/`.fini`) and mark it `skipped` with module `crt`.
3. **`main` isn't named.** **Cause:** stripped binary. **Fix:** follow `entry` to the `__libc_start_main` call
   (its first argument is `main`) or find the function that references the program's usage strings.
4. **Speed reference:** an 18 KB stripped x86-64 ELF: import, analysis and both scripts in about 9 s on a
   laptop. Budget minutes to hours for large games; run it once and keep the project (`ghidra/`).
5. **Decompiler output must never be committed.** **Cause:** it's derived from the original. **Fix:** write it
   under `build/` (gitignored by `ud init`); `ud publish check` and `ud kb check` catch leaks.

## Seen in
`examples/tinyquest/reconstruction/DECOMPLOG.md`.
