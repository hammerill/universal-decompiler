---
name: reverse-engineering
description: Read how a binary actually works so it can be reconstructed - Ghidra driven through pyghidra-mcp (decompile, rename, retype, structs, vtables, RTTI, cross-references), headless Ghidra exports, managed decompilers (ilspycmd, Cpp2IL, Vineflower, PyLingual), and proving a file format with a round trip. Use when a decompilation needs function-level understanding ("what does this function do", "rebuild this struct", "name these functions", "what format is this archive"), or to set up Ghidra/pyghidra-mcp for an agent.
---

# Reverse engineering for reconstruction

Rule zero: **read the real thing, don't guess.** The decompiler output and the original's behaviour are the
spec. Write what you learn into `DECOMPLOG.md` as you go (addresses, names, struct offsets, formats).
Decompiler output stays in the gitignored `build/`; never commit it and never paste it into `knowledge/`.

## Ghidra through pyghidra-mcp
Setup (once per repo; `ud tools check --route native` first):
```bash
ud mcp pyghidra --agent <claude|codex|cursor|gemini|vscode|opencode> --write
sh tools/start-pyghidra-mcp.sh          # Windows: tools\start-pyghidra-mcp.ps1; leave it running
```
pyghidra-mcp serves `http://127.0.0.1:8000/mcp` (streamable HTTP, the transport its README recommends) and
analyses the binary into `ghidra/` (gitignored: a Ghidra project embeds the binary). Reload the agent if its
tools don't appear. If port 8000 is already in use, someone else's server is there: don't touch it, pass
`--port`.

Tools you'll use most (names from the pyghidra-mcp README, 0.2.7):
- reading: `decompile_function` (by name or address, batch-capable, can attach callees/strings/xrefs),
  `list_xrefs`, `search_symbols_by_name`, `search_strings`, `search_code`, `gen_callgraph`,
  `list_imports`, `list_exports`, `read_bytes`, `list_project_binary_metadata`;
- writing: `rename_function`, `rename_variable`, `set_variable_type`, `set_function_prototype`,
  `set_comment`.

Inventory for the tracker: save `search_symbols_by_name(binary, ".*", functions_only=True, limit=...)`
(paginate with `offset`) as JSON and `ud funcs import` it.

## Ghidra headless (no MCP, CI, big batches)
```bash
"$GHIDRA_INSTALL_DIR/support/analyzeHeadless" ghidra <project> -import data/<binary> \
  -scriptPath "<universal-decompiler>/ud/ghidra" \
  -postScript ExportFunctions.java build/functions.json \
  -postScript DecompileAll.java build/decomp
# later runs on the analysed program: -process <binary> -noanalysis
ud funcs import build/functions.json
```
On Windows use `analyzeHeadless.bat`. 32-bit console code: pass `-processor` (e.g. `MIPS:BE:32:default`)
and `-loader` when the auto-detected one is wrong.

## The workflow per function
1. **Find it**: strings -> cross-references -> function; imports (file I/O, graphics, input) -> callers; the
   entry point -> the main loop -> subsystems. Name the big structure first (main loop, update, render,
   load), details later.
2. **Understand it**: decompile; follow callees one level; identify library code (CRT, STL, middleware) and
   mark it `skipped` instead of porting it.
3. **Name and type it in Ghidra**: functions, parameters, locals, globals. Create structs from field
   offsets (`*(int *)(p + 0xe8)` -> a field at 0xE8), apply them to parameters, re-decompile: the code gets
   readable fast. Enums for magic constants.
4. **Confirm before building on it**: agents misidentify things confidently. Check a hypothesis against the
   running original (a debugger breakpoint, a logged value, an input that should trigger it).
5. **Record it**: `ud funcs set <addr> --name <name> --status reversed --note "<one line>"`, and the
   struct layout in `DECOMPLOG.md`.

## C++ specifics
- **RTTI** (MSVC `.?AV<class>@@` type descriptors, GCC `_ZTS`/`_ZTI`) gives class names and hierarchy even in
  stripped binaries; vtables follow the type info. Ghidra's RTTI analyzers apply them; name each vtable slot
  as you identify it.
- **Vtables**: an array of function pointers in `.rdata`; the constructor stores its address at offset 0 of
  the object. Calls through `(**(code **)(*this + 0x18))(this)` are virtual calls to slot 6 (x64).
- **thiscall** (x86 MSVC): `this` in ECX; Ghidra shows `__thiscall`. Member functions cluster by class in
  the binary.
- **Templates/STL**: identify the library and version (`std::vector` growth patterns, `std::string` SSO
  layout differ between MSVC and libstdc++) and replace with the real STL.

## Managed and bytecode decompilers
| Code | Tool | Command |
|---|---|---|
| .NET / XNA / FNA / Unity Mono | ilspycmd | `ilspycmd -p -o build/decompiled data/Game.exe` |
| Unity IL2CPP | Cpp2IL (+ Ghidra for bodies) | `Cpp2IL --game-path=data/ --output-as=dummydll` |
| Java | Vineflower | `java -jar $VINEFLOWER_JAR data/Game.jar build/decompiled/` |
| Python (PyInstaller...) | pyinstxtractor + PyLingual (+ pycdc) | `pyinstxtractor-ng data/App.exe`, then `pylingual <file.pyc>` |
| Godot | GDRE Tools | `gdre_tools --headless --recover=data/game.pck --output-dir=build/recovered` |
| GameMaker | UndertaleModCli | export scripts on `data.win` |
| Ren'Py | rpatool + unrpyc | `python rpatool -x game/archive.rpa`, `python unrpyc.py game/` |

## Proving a file format with a round trip
1. Collect several files of the format from the user's copy. Hex-dump headers (`xxd | head`); look for
   magic numbers, counts, offset tables, fixed-size records.
2. Find the reader in the binary (the function that opens the file: strings with the extension, `fopen`/
   `CreateFile` xrefs) and read the format from it: that's the authoritative spec.
3. Write a reader in `tools/extract_assets.py`; parse **every** file of the format without errors; decode to
   something viewable (PNG, WAV, JSON) and look at it.
4. If the program needs it, write the encoder and prove it: decode -> encode -> decode equals the original.
5. Document the format in the script's docstring (as `examples/tinyquest/reconstruction/tools/
   extract_assets.py` does).

## Long runs
- One function at a time; log every confirmed fact; cap attempts per problem (3 identical failures: change
  approach or ask: the circuit breaker).
- Keep the Ghidra project's renames in sync with `decomp/progress.json` names; the tracker is what survives
  context compaction.
