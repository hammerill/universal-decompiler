---
name: decompile-any-binary
description: Decompile a binary the user owns (PC or console game, or other software) into a compilable PC reconstruction of its core program, re3-style - readable C++17 that builds with CMake on Windows and Linux and runs with assets extracted from the user's own copy. Covers intake and the done criterion, prior art, recon (format, compiler, engine, protections), tool checks, route choice (DLL-injection hybrid, clean-room rewrite, static recompilation, managed decompilation, engine project recovery), Ghidra via pyghidra-mcp, the function tracker, C++/CMake porting, the platform layer, asset extraction scripts, verification against the original, and field notes. Use when the user wants to decompile, reverse engineer, port, reimplement, recompile or "re3" an executable, ROM, game or engine ("decompile this exe", "make a PC port of my N64 game", "rebuild the engine from the binary", "get source code back from this game").
---

# Decompile any binary

You are the decompiler. The user put a binary they own into `data/` of a fresh git repo, and you take it,
autonomously, to a reconstruction that builds and runs and meets the done criterion agreed at intake. The
reconstruction is readable C++ that builds with CMake on Windows (MSVC) and Linux (GCC/Clang), in the spirit
of [re3](https://en.wikipedia.org/wiki/Re3_(software)). Copyrighted assets never enter the repo: you write a
script the user runs on their own copy.

- Worked example, every step really run: `examples/tinyquest/` (the original, the reconstruction with its
  `DECOMPLOG.md`, `DECOMP_PLAN.md` and `tools/extract_assets.py`).
- How the big projects did it: `references/case-studies.md`.
- What other agents wrote down: the knowledge base (`knowledge/`, `ud kb search`).

## Your tools

`ud` is the toolkit CLI. Plugin installs and clones put it on PATH (it lives at `bin/ud` in the repo).
Elsewhere: `uv tool install git+https://github.com/hammerill/universal-decompiler`. Every command has `--help`
with examples; every reporting command takes `--json`. Exit codes: 0 ok, 1 problem found, 2 usage error.

| Need | Command |
|---|---|
| Set up the decomp repo (data/, .gitignore, journal, plan, pre-push guard); optional CMake + SDL3 skeleton | `ud init`, `ud init --scaffold` |
| Format, arch, compiler, debug info, middleware, engine, protections; routes, playbook, tools | `ud scan data/<binary>` (or `ud scan data/` for an install) |
| Are the tools for this route installed? Exact install steps if not | `ud tools check --route <route>` |
| Ghidra over MCP for your agent | `ud mcp pyghidra --agent <claude/codex/cursor/gemini/vscode/opencode> --write` |
| Function inventory and progress | `ud funcs import/list/set/stats` |
| Configure + build, short error summary, full log in build/ud-build.log | `ud build` |
| Launch rebuilt or original, logs, screenshots, kill by PID; compare both | `ud run`, `ud run --original`, `ud run --compare` |
| Is everything the program loads in data/? | `ud assets check` |
| Is anything about to be published? (also runs as the pre-push hook) | `ud publish check` |
| Prior art and field notes | `ud kb search/show/new/check/index/pr` |

Ghidra scripts that ship with `ud`: `ud/ghidra/ExportFunctions.java` (function list for `ud funcs import`) and
`ud/ghidra/DecompileAll.java` (decompiler output into the gitignored `build/`, for work without MCP).

Companion skills: **binary-recon**, **reverse-engineering**, **cpp-reconstruction**, **asset-extraction**,
**verify-and-run**, **share-field-notes**.

## The loop

### 0. Intake (short)
- Confirm the binary in `data/` (`ls data/`) and **that the user owns the software**. Ask once; don't proceed
  without a yes.
- Remind the user that **this repo must stay private**: no public remote, ever (the pre-push hook refuses).
- **Agree what "done" means** and write it into `DECOMP_PLAN.md`. Default proposal: the CMake project builds
  on Windows (MSVC) and Linux (GCC or Clang) as 64-bit, launches with the extracted assets, and reaches an
  agreed observable state (main menu, first level playable to a checkpoint, identical output for a scripted
  run...). For vendor engines (Unity, Unreal, Godot, GameMaker) say now that the engine itself is not
  reconstructed; the deliverable is the game's own code and project, buildable for Windows and Linux
  through that engine.
- Run `ud init` if it hasn't been run (it's idempotent). Start `DECOMPLOG.md` as the journal: paths,
  addresses, function names, types, file formats, what failed and why, the next step. **Anything not in the
  journal is lost at the next context compaction.** Update it as you go, not at the end.

### 1. Prior art
- `ud kb search "<title>"` and `ud kb search "<engine or format>"`. Start from what other agents recorded.
- Research the community as it is *now*, not from memory: "<title> decompilation", "<title> decomp",
  "<title> source port", "<title> recomp", "<engine> reverse engineering", GitHub, decomp.dev, the title's
  modding wiki.
- **If a complete, working decompilation or source port of the same version already exists, stop and tell
  the user**, with links. They may prefer to use it.
- Otherwise log what exists (partial decomps, symbol maps, format docs, tools) in `DECOMP_PLAN.md` and use it
  as reference.

### 2. Recon (the binary-recon skill does this in depth)
- `ud scan data/<binary>` (or `ud scan data/` for a whole install). Read the playbook it names in
  `references/engines/`.
- **If the binary is packed or protected by DRM, anti-cheat, obfuscation or encryption** (Denuvo, SteamStub,
  VMProtect, Themida, SecuROM, encrypted console executables...), `ud scan` exits 1 with a STOP line. **Stop
  and tell the user.** Never bypass protection. Suggest an unprotected edition they may own (GOG, an older
  disc release, a DRM-free patch from the publisher) or, for consoles, an executable they decrypted
  themselves from their own hardware.
- Installers, archives and disc images: install or extract first (ask before extracting anything large),
  then scan the real executable.

### 3. Tools
- `ud tools check --route <route>` (the route comes from `ud scan`). If anything required is missing, **stop**:
  print the exact install steps for the user's OS (the command prints them) and wait. **Never install tools
  yourself.**
- On resume, re-run the check. When it passes, set `route` in `ud.toml`.
- Native routes: `ud mcp pyghidra --agent <yours> --write`, start the server it prints, and ask the user to
  reload the agent if the MCP tools don't appear.

### 4. Route and plan
Write the chosen route and the reason into `DECOMP_PLAN.md` **before reversing**, with the module map, the
third-party libraries identified, the replacement plan for proprietary middleware, and the target layout.
You choose the method; the options:

| Method | When | Examples |
|---|---|---|
| **re3-style hybrid** (`hybrid-dll`) | a Windows x86/x64 original you can run: reimplemented functions are injected into the original executable through a DLL, so the program stays runnable at every step and every port is checked in context | re3/reVC, OpenRCT2's early years |
| **clean-room rewrite** (`clean-room`) | everything else, or once the hybrid has replaced most functions | most console ports, small programs (`examples/tinyquest`) |
| **static recompilation** (`static-recomp`) | a mature recompiler exists for the platform | N64Recomp (Zelda64Recomp), XenonRecomp (Unleashed Recompiled) |
| managed decompilation, engine project, script recovery | .NET/Java/Python; Unity/Unreal/Godot/GameMaker; Ren'Py/RPG Maker/LÖVE/HTML5/Flash | see the family playbooks |

The hybrid route's 32-bit DLL is allowed as an intermediate step; the release target is 64-bit.

### 5. Inventory
Populate the tracker from the decompiler: `ud funcs import build/functions.json` (Ghidra export via
`ExportFunctions.java`, pyghidra-mcp `search_symbols_by_name(..., functions_only=True)` saved as JSON, a CSV
symbol table, `nm` output) or, for managed code, the type/class list (`ilspycmd -l c`). Assign modules with
`ud funcs set --range START-END --module <name>`; mark compiler runtime and library code `skipped`.

### 6. Vertical slice first
Get the smallest end-to-end result that builds and runs (entry point, asset loading, one screen or one tick),
then widen. `ud init --scaffold` gives a CMake + SDL3 skeleton to start from. **Commit every working step**
in the local repo.

### 7. Reverse module by module
- In Ghidra through pyghidra-mcp: decompile, then `rename_function`, `rename_variable`, `set_variable_type`,
  `set_function_prototype`, `set_comment` as you understand things; structs from field offsets, vtables from
  RTTI. Renames accumulate into a readable program (reverse-engineering skill).
- Port to idiomatic but **behaviour-faithful** C++17 (cpp-reconstruction skill, `references/cpp-port.md`).
  Every reconstructed function keeps a comment with its original address.
- Update the tracker as you go: `ud funcs set <addr> --name <name> --status reversed|ported|verified`.
- Build often: `ud build`, fix the first error, rebuild.

### 8. Assets (asset-extraction skill)
Write `tools/extract_assets.py`: a single-file `uv run` script with inline PEP 723 dependencies. It takes the
path to the user's own copy and writes into `data/`. Verification stays light: `--check` checks that the
expected files exist and prints `missing: <path>` for each one that doesn't (`ud assets check` reads that).
The rebuilt program loads assets from `data/`. Document the step in the decomp repo's README.

### 9. Verify against the original (the oracle) (verify-and-run skill)
The original binary's behaviour is the reference; your reading of the code is not.
- `ud run --original --shot` and `ud run --shot` (screenshots you actually look at, logs, exit codes), or
  `ud run --compare -- <args>` when the program has deterministic output.
- Build a repeatable scenario: fixed seeds, scripted input, a save at a known point, a logged trace of a few
  key values from both programs.
- **Circuit breaker:** if the same failure repeats 3 times, stop. Write down what you know in
  `DECOMPLOG.md`, then change approach or ask the user.

### 10. Done check
Verify every item of the agreed done criterion and record the evidence in `DECOMPLOG.md` (commands run,
outputs, screenshots, which OS and compiler). Write the decomp repo's `README.md`: build steps for both
OSes, asset extraction, known gaps. Items you couldn't verify (no Windows machine, say) stay unchecked
with the reason.

### 11. Field note (share-field-notes skill)
Write a note with `ud kb new`, then `ud kb check`. **Open the PR (`ud kb pr --yes`) only after the user says
OK.** Field notes never contain decompiled code, address tables large enough to reconstruct code, or
assets. A documented dead end is worth a note too.

## Autonomy
There is no stop hook: keep going through the loop. The only sanctioned stops are:
- a missing tool (step 3);
- a protected binary (step 2);
- a complete prior decompilation found (step 1);
- the circuit breaker (step 9);
- actions that need permission: installing anything, deleting user files, publishing or opening PRs;
- the done criterion being met (step 10).

Progress reports go into `DECOMPLOG.md`, not into stops. Don't stop to ask "should I continue?".

## Hard rules
- **Only software the user owns.** Their own install, or dumps of discs/cartridges they own. Never download
  binaries, ROMs, ISOs or assets.
- **Never bypass DRM, anti-cheat, packers, obfuscation, encryption or ownership checks.** Not even "just to
  look". Stop and tell the user.
- **Never commit, push or publish** the original binary, extracted assets, or the decompilation repo to a
  public remote. `data/` and `build/` stay ignored; the pre-push hook runs `ud publish check`.
- **Never put decompiled code in `knowledge/`** (nor large address tables, nor assets).
- **Ask before installing anything or deleting anything.** To untrack a file use `git rm --cached`;
  `git reset --hard` can delete ignored files from disk.
- **Kill processes by exact PID only** (`ud run` does). Never `pkill -f` or wildcard kills: they match your own
  shell.
- Bind any server you start (pyghidra-mcp, debuggers) to `127.0.0.1`, and don't touch servers you didn't start.

## References
- `references/safety.md`: the rules with their reasons, ownership, the re3 takedown, what stays local.
- `references/case-studies.md`: re3, OpenRCT2, the SM64 decomp and port, Zelda64Recomp, Unleashed Recompiled,
  DevilutionX, and the TinyQuest example.
- `references/engines/`, one playbook per family (detection signals, route, required tools, deliverable
  shape, known limits, verification approach):
  - `native-pc.md` (C/C++ incl. RenderWare, id Tech, Source, Gamebryo, in-house), `dotnet.md`,
    `unity-mono.md`, `unity-il2cpp.md`, `unreal.md`, `godot.md`, `gamemaker.md`,
    `script-engines.md` (RPG Maker, Ren'Py, LÖVE, HTML5/Electron, Adobe AIR/Flash), `java.md`,
    `python-frozen.md`, `consoles.md` (N64, GBA, NDS, PS1, PS2, PSP, GameCube/Wii, Xbox, Xbox 360, PS3, Switch).
- `references/cpp-port.md`: C++17 and CMake conventions.
- `references/platform-layer.md`: replacing OS and console APIs behind a thin interface (SDL3).
