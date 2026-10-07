# universal-decompiler

**Skills, the `ud` CLI and a shared knowledge base that let an AI coding agent take a binary you own (a PC
or console game, or any other program) and produce, on its own, a compilable PC reconstruction of its core
program**: readable C++ that builds
with CMake on Windows, Linux and macOS and runs with the assets extracted from your own copy.

Inspired by universal-modder. Not affiliated with its authors.
([universal-modder](https://github.com/rehan-remade/universal-modder) by rehan-remade, MIT; this project
mirrors its architecture: skills + CLI + knowledge base + journal + circuit breaker. See [`NOTICE`](NOTICE).)

## How you use it
1. Create a folder for the decompilation and run `git init` in it.
2. Create `data/` and put the binary there (and, optionally, the rest of the install). `ud init` gitignores it.
3. Start your agent in that folder with the universal-decompiler skill loaded and `ud` on PATH (see Install).
4. Say what you want:
   > Decompile the game in data/ into a C++ reconstruction that builds on Windows, Linux and macOS.
5. The agent confirms that you own the software, agrees with you what "done" means (by default: builds
   with MSVC, GCC/Clang and Apple Clang as 64-bit, launches with your extracted assets, reaches an agreed point such as
   the main menu), and writes it into `DECOMP_PLAN.md`. Then it runs recon (`ud scan`), checks for prior
   work, and checks the tools for the route (`ud tools check`). **If a tool is missing it stops and gives you
   exact install steps; it never installs anything itself.** If the binary is protected (DRM, packer,
   anti-cheat, encryption) it stops and tells you; it never bypasses protection.
6. Then it works autonomously until the done criterion is met: inventory of functions, a vertical slice,
   module by module through Ghidra (via pyghidra-mcp), a script that extracts the assets from your copy,
   and verification against the original. Its journal is `DECOMPLOG.md`.

The decompilation repo is **for local management only**: a pre-push hook refuses to push the original,
extracted assets, or anything to a public remote.

## Install

Pick your agent. Each gets the same skills (Agent Skills format) and the `ud` CLI. universal-decompiler ships
no MCP server of its own; `ud mcp pyghidra` configures the third-party
[pyghidra-mcp](https://github.com/clearbluejar/pyghidra-mcp) server for your agent, in your decomp repo.

| Agent | Install |
|---|---|
| **Claude Code** | `/plugin marketplace add hammerill/universal-decompiler`<br>`/plugin install universal-decompiler@universal-decompiler` |
| **Codex** | `codex plugin marketplace add hammerill/universal-decompiler`<br>`codex plugin add universal-decompiler@universal-decompiler` |
| **Gemini CLI** | `gemini extensions install https://github.com/hammerill/universal-decompiler` |
| **VS Code / Copilot** | Enable `chat.plugins.enabled`, run **Chat: Install Plugin From Source**, and enter this repo's URL |
| **Cursor** | Cursor Marketplace, or clone (Cursor reads `AGENTS.md` and `.agents/skills`) |
| **OpenCode** | Clone and run `opencode` inside it (`opencode.json` points it at `skills/`) |
| **Skills only**<br>(any agent) | `npx skills add https://github.com/hammerill/universal-decompiler` |
| **Anything else** | `git clone https://github.com/hammerill/universal-decompiler` and start your agent with it |

Inside a clone, agents find the skills where they look for them: `.agents/skills` (Codex, Gemini CLI,
Copilot, Cursor, OpenCode) and `.claude/skills` (Claude Code) are copies of `skills/`. Instructions are in
`AGENTS.md`, which `CLAUDE.md` and `GEMINI.md` point to.

**The `ud` CLI.** Plugin installs and clones put it on PATH (a SessionStart hook adds `bin/`). Anywhere else:
```bash
uv tool install git+https://github.com/hammerill/universal-decompiler      # or: pipx install git+...
```
It needs Git and Python 3.12+ (`uv` recommended; `bin/ud` bootstraps its environment with uv). The tools
for each route (Ghidra, a JDK, pyghidra-mcp, CMake, a C++ compiler, ilspycmd, AssetRipper, splat, ...) are
listed by `ud tools check --route <route>` with install steps for Windows, Linux and macOS.

## What's inside

**Skills** (`skills/`, Agent Skills format)

| Skill | What it does |
|---|---|
| [`decompile-any-binary`](skills/decompile-any-binary) | The whole loop (intake and the done criterion, prior art, recon, tools, route, inventory, vertical slice, module by module, assets, verification, done check, field note), the autonomy rules and hard rules, and **11 family playbooks**: native PC (incl. RenderWare, id Tech, Source, Gamebryo, in-house), .NET/XNA/FNA/MonoGame, Unity Mono, Unity IL2CPP, Unreal 3/4/5, Godot, GameMaker, script engines (RPG Maker, Ren'Py, LÖVE, HTML5/Electron, AIR/Flash), Java, Python frozen apps, consoles (N64, GBA, NDS, PS1, PS2, PSP, GameCube/Wii, Xbox, Xbox 360, PS3, Switch) |
| [`binary-recon`](skills/binary-recon) | Prior art, format, arch, compiler, symbols, engine, protections, route -> `DECOMP_PLAN.md` |
| [`reverse-engineering`](skills/reverse-engineering) | Ghidra through pyghidra-mcp (naming, typing, structs, vtables, RTTI), headless exports, managed decompilers, proving a file format with a round trip |
| [`cpp-reconstruction`](skills/cpp-reconstruction) | Decompiler output -> buildable C++17 with CMake, the platform layer (SDL3), middleware replacement, the re3-style DLL hybrid, 32 -> 64-bit pitfalls |
| [`asset-extraction`](skills/asset-extraction) | `tools/extract_assets.py` (single-file `uv run` script, PEP 723), reverse-engineering archive formats |
| [`verify-and-run`](skills/verify-and-run) | Building, launching, logs, screenshots, comparison with the original, the circuit breaker |
| [`share-field-notes`](skills/share-field-notes) | Search the knowledge base, write a note, open the PR (with your OK) |

**The `ud` CLI** (Python). Every command has `--help` with examples; every reporting command takes `--json`;
exit codes are 0 ok, 1 problem found, 2 usage error.

| Command | What it does |
|---|---|
| `ud init` | In the current git repo: `data/`, a managed `.gitignore` block, `DECOMPLOG.md`, `DECOMP_PLAN.md`, `ud.toml`, and a pre-push hook running `ud publish check`. Idempotent. `--scaffold` adds a CMake + SDL3 platform-layer skeleton |
| `ud scan <path>` | Format (PE/COFF with Rich header and PDB path, ELF, Mach-O, XBE, XEX, SELF, DOL/REL, NSO/NRO/NSP, PS-X EXE, ROMs, disc images, .NET, JARs, archives), arch, compiler, debug info, middleware, engine, protections; ranked routes with the tools each needs and the playbook to read. A file or an install folder |
| `ud tools check [--route R]` | Each tool the route needs: found or not, version, and exact install steps for Windows, Linux and macOS. Never installs. Registry: `ud/tools.toml` |
| `ud mcp pyghidra [--agent A] [--write]` | The pyghidra-mcp config for Claude Code, Codex, Cursor, Gemini CLI, VS Code or OpenCode, plus a start script with `GHIDRA_INSTALL_DIR` |
| `ud funcs import\|list\|set\|stats` | The function tracker in `decomp/progress.json`: imports Ghidra/pyghidra-mcp exports, symbol tables, `nm` output or managed type lists; coverage per module |
| `ud build [--config Debug\|Release]` | Configure + build with CMake; full log in `build/ud-build.log`, short `file:line: message` summary |
| `ud run [--shot] [--timeout S] [--original] [--compare]` | Launch the rebuilt program or the original, capture stdout/stderr and logs, take window screenshots (Windows, also from WSL; Linux X11/Wayland best effort; macOS whole screen), kill by exact PID at the timeout; `--compare` runs both and diffs the output |
| `ud assets check` | Runs `tools/extract_assets.py --check` and reports what's missing in `data/` |
| `ud publish check` | Fails if the repo's history holds the original, extracted assets, Ghidra projects or large binaries, or if a remote is a public repository. The pre-push hook |
| `ud kb search\|show\|new\|check\|index\|sync\|pr` | The knowledge base; `check` rejects decompiled code, long code blocks and large address tables |

Ghidra scripts for headless work ship in `ud/ghidra/`: `ExportFunctions.java` (for `ud funcs import`) and
`DecompileAll.java` (decompiler output into the gitignored `build/`).

## Worked example
[`examples/tinyquest`](examples/tinyquest): a small C++ program (a tiny game engine with its own archive
format) compiled to a stripped binary, reversed with Ghidra 12.1.4 through `ud`, and rebuilt as C++17/CMake
that prints exactly what the original prints. It includes the reconstruction's `DECOMPLOG.md`,
`DECOMP_PLAN.md` and `tools/extract_assets.py` for its dummy asset pack. CI builds the original and the
reconstruction on Windows (MSVC), Linux (GCC) and macOS (Apple Clang, arm64) and compares their output on seven argument sets. No
commercial binaries anywhere in the repo.

## A knowledge base that agents write for agents
[`knowledge/`](knowledge/) holds **field notes**: how specific binaries were decompiled, one note per title
or topic, with exact versions, the route and why, what the engine really does, how it was verified, and
gotchas (symptom -> cause -> fix). It starts with notes on tooling (pyghidra-mcp setup, Ghidra headless,
reading optimised decompiler output, oracle comparisons).
```bash
ud kb search "renderware"            # before you start (works outside the repo too: it syncs from GitHub)
ud kb new --subject "Foo Racer" --title "Hybrid DLL reconstruction of Foo Racer 1.2" --from-scan data/foo.exe
ud kb check knowledge/foo-racer/hybrid-dll-reconstruction-of-foo-racer-1-2.md
ud kb pr knowledge/foo-racer/hybrid-dll-reconstruction-of-foo-racer-1-2.md --yes   # only after you say OK
```
Rules for contributors, human or AI, are in [`CONTRIBUTING.md`](CONTRIBUTING.md): no binaries, no assets,
no decompiled code, honest status.

## Legal and safety posture
- universal-decompiler is for **software you own**, for interoperability, preservation and study.
- **Decompiled output and extracted assets stay local.** Nothing copyrighted is ever part of the output: the
  agent writes a script that you run on your own copy to extract the assets into `data/`.
- **Publication is blocked on purpose.** re3, a reconstruction of GTA III that shipped no game assets, was
  taken down by a DMCA notice in 2021 all the same (and its authors were sued). That's why `ud publish check`
  runs before every push and refuses public remotes.
- It never bypasses DRM, anti-cheat, packers, obfuscation, encryption or ownership checks, never downloads
  binaries or assets, asks before installing or deleting anything, and kills processes by exact PID only.

This is not legal advice. Full reasoning:
[`skills/decompile-any-binary/references/safety.md`](skills/decompile-any-binary/references/safety.md).

## Contributing and development
```bash
uv run pytest                     # tests (synthetic fixtures generated in-test; the example end to end if a compiler is present)
uv run ruff check                 # lint
python scripts/sync_skills.py     # after editing skills/
./bin/ud kb check --index         # knowledge base
```
Decisions, tool substitutions and what failed along the way are in [`DEVLOG.md`](DEVLOG.md).

## Credits
- Inspired by [universal-modder](https://github.com/rehan-remade/universal-modder) (not affiliated).
- Standing on Ghidra, pyghidra-mcp, ILSpy, AssetRipper, Cpp2IL, GDRE Tools, UndertaleModTool, Vineflower,
  PyLingual, pycdc, splat, decomp-toolkit, N64Recomp, XenonRecomp, SDL, and every reconstruction project that
  showed how it's done: re3, OpenRCT2, the SM64 decompilation, Zelda64Recomp, Unleashed Recompiled,
  DevilutionX.

MIT licensed ([`LICENSE`](LICENSE)).
