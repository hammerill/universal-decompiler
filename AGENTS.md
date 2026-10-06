# universal-decompiler

A decompilation toolkit and a shared knowledge base for AI coding agents: Claude Code, Codex, Cursor,
Gemini CLI, GitHub Copilot, OpenCode and anything else that reads `AGENTS.md`. When someone opens an agent
with this toolkit, they almost always want to **decompile a binary they own into a compilable PC
reconstruction**, or to learn how something was decompiled.

## Start here
1. **Read `skills/decompile-any-binary/SKILL.md` and follow its loop:** intake (ownership, done criterion,
   privacy) -> prior art -> recon (`ud scan`) -> tools (`ud tools check`) -> route and plan -> inventory
   (`ud funcs`) -> vertical slice -> module by module -> assets (`tools/extract_assets.py`) -> verify against
   the original (`ud run`) -> done check -> field note.
2. **Search the knowledge base first:** `ud kb search "<title, engine or tool>"` (`knowledge/INDEX.md`).
3. **At the end, share what you learned:** `ud kb new ...`, `ud kb check`, and with your human's OK,
   `ud kb pr <note> --yes`. See `knowledge/README.md` and `CONTRIBUTING.md`.

## The user's decomp repo
The user creates a folder, runs `git init`, puts the binary (and optionally its install) into `data/`, and
starts you there with this toolkit loaded. `ud init` sets it up: `data/` and `build/` ignored, `DECOMPLOG.md`
(the journal) and `DECOMP_PLAN.md` (done criterion, route, module map), `ud.toml`, and a pre-push hook that
runs `ud publish check`. The repo is for local management only and must never go to a public remote.

## Tools
- **`bin/ud`** is the Python CLI (Python >= 3.12); it sets itself up with `uv`.
  - On PATH: plugin installs and the SessionStart hook do it; otherwise `export PATH="$PWD/bin:$PATH"`, or
    `uv tool install git+https://github.com/hammerill/universal-decompiler`.
  - Groups (every one has `--help` with examples; reporting commands take `--json`; exit codes 0 ok,
    1 problem found, 2 usage error): `init`, `scan`, `tools`, `mcp`, `funcs`, `build`, `run`, `assets`,
    `publish`, `kb`.
- **No MCP server of our own.** `ud mcp pyghidra` writes the config for the third-party pyghidra-mcp server
  into the user's decomp repo (per agent).
- **Skills** (`skills/*/SKILL.md`, Agent Skills format) are copied where agents look for them in a clone:
  `.agents/skills` (Codex, Gemini CLI, Copilot, Cursor, OpenCode) and `.claude/skills` (Claude Code). Edit
  `skills/`, then run `python scripts/sync_skills.py`; a test fails while the copies differ.
- **Family playbooks:** `skills/decompile-any-binary/references/engines/`.
- **Worked example:** `examples/tinyquest/` (original, reconstruction, end-to-end check).

## Rules (reasons in `skills/decompile-any-binary/references/safety.md`)
- **Only software the user owns.** Never download binaries, ROMs, ISOs, BIOS/firmware or assets.
- **Never bypass DRM, anti-cheat, packers, obfuscation, encryption or ownership checks.** `ud scan` stops on
  them; tell the user.
- **Never commit, push or publish** the original, extracted assets, or the decomp repo to a public remote.
- **Never put decompiled code in `knowledge/`** (nor large address tables, nor assets).
- **Ask before installing or deleting anything.** `ud tools check` prints install steps; it never installs.
- **Kill processes by exact PID only** (`ud run` does). Never `pkill -f`.
- **Keep the journal** (`DECOMPLOG.md`): anything not in it is lost at the next context compaction.
- **Circuit breaker:** the same failure 3 times -> stop, write down what you know, change approach or ask.

## Working on the toolkit itself
- **Python:** 3.12+, one runtime dependency (PyYAML), managed with `uv`. Code lives in `ud/`, one module per
  CLI group, each with `register(sub)` and a docstring that doubles as `--help`. The tool registry is
  `ud/tools.toml` (adding a tool or route needs no code change). Ghidra scripts are in `ud/ghidra/`,
  templates in `ud/templates/`.
- **Windows tools:** `ud/ps1/*.ps1` embed C# 5 (Windows PowerShell 5.1's compiler): no string interpolation,
  no `out var`, no expression-bodied members.
- **Tests:** `uv run pytest`. Lint: `uv run ruff check`. CI (Windows + Ubuntu) also runs `ud kb check
  --index`, the skills-sync check and the TinyQuest example end to end.
- **Journal:** `DEVLOG.md` records every non-obvious decision and tool substitution.
- **Wording:** keep skills and docs agent-neutral ("the agent") except in sections about one agent.
