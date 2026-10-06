# DEVLOG

Build journal for universal-decompiler: decisions, what failed and why, next step. Newest entries at the
bottom of each day. If you are an agent resuming after a context compaction, read this first.

## 2026-10-06

### Study of universal-modder (commit 76b9c7e)
Cloned `rehan-remade/universal-modder` outside the repo and read the docs, skills, hooks, `bin/um`, the
`um/` package, the tests and the per-agent manifests. Things mirrored here on purpose:
- `skills/` is the source of truth; `.claude/skills` and `.agents/skills` are real copies (no symlinks, so
  Windows clones work) and a test fails while they differ.
- `AGENTS.md` is canonical; `CLAUDE.md` and `GEMINI.md` import it with `@AGENTS.md`.
- `bin/um` is a bash launcher that runs `uv run --project <root> python -m um`; the SessionStart hook
  (`hooks/hooks.json` for the plugin, `.claude/settings.json` for a clone) appends `<root>/bin` to PATH via
  `$CLAUDE_ENV_FILE`. `ud` copies that exactly.
- One module per CLI group with `register(sub)` and a docstring that doubles as `--help`.
- Knowledge base: Markdown + YAML front matter, generated `INDEX.md` + `index.json`, `kb check` lint,
  `kb pr` that forks/pushes/opens a PR only with `--yes` after the human agrees.
- Autonomy: journal file (`MODLOG.md` there, `DECOMPLOG.md` here), circuit breaker after 3 identical
  failures, no Stop hook.

Differences, decided:
- **No MCP server of our own and no MCP config in this repo.** universal-modder ships `.mcp.json`,
  `.codex/config.toml`, `.cursor/mcp.json`, `.vscode/mcp.json` for fal. We have nothing to serve, so those
  files are absent; `ud mcp pyghidra` writes the equivalent files *into the user's decomp repo* instead.
  The Codex and Gemini manifests therefore have no `mcpServers` entry.
- Python >= 3.12 (spec) instead of >= 3.10. Only runtime dependency: PyYAML (knowledge-base front matter).
  `tomllib` (stdlib) reads `ud/tools.toml`.
- No media (logos, banners): the Codex manifest's `composerIcon`/`logo` fields are omitted rather than
  pointing at placeholder art.
- Added `bin/ud.cmd` next to `bin/ud` so a native Windows shell (cmd/PowerShell, CI) can run the launcher;
  universal-modder only has the bash launcher (its Windows path is Git Bash).

### Tool verification (sources checked today, 2026-10-06)
Checked on GitHub (repo status, latest release redirect), PyPI, npm and Maven Central. Results that shape
`ud/tools.toml`:
- Ghidra **12.1.4** (latest release). 12.1 needs **JDK 21** 64-bit; `master` (12.2) moves to JDK 25, so the
  install steps say "JDK 21 or newer" and the check accepts either.
- pyghidra-mcp **0.2.7** (PyPI, Python >= 3.10). Its README recommends streamable HTTP
  (`pyghidra-mcp --transport streamable-http --project-path ... <binary>`, served at
  `http://127.0.0.1:8000/mcp`), with stdio for hosts that can't do HTTP; needs `GHIDRA_INSTALL_DIR`. The
  Claude Code config needs `"type": "http"` (an entry with only `url` is read as stdio). `ud mcp` follows
  that README, not memory.
- ilspycmd **10.1.1** (`dotnet tool install --global ilspycmd`).
- AssetRipper **2.0.0** (zip per OS: `AssetRipper_win_x64.zip`, `AssetRipper_linux_x64.zip`).
- Cpp2IL: maintained (pushed 2026-09). **Il2CppDumper: last push 2024-08 → treated as unmaintained.**
  Substitution: Cpp2IL is the primary IL2CPP tool; Il2CppDumper stays as an optional fallback only.
- FModel (release `aug-2026`) is **Windows-only** (.NET WPF); `tools.toml` marks it `platforms=["windows"]`.
- RE-UE4SS **3.0.1**, GDRE Tools **2.7.0** (has `--headless --recover=`), UndertaleModTool **0.9.2.0**
  (also ships UndertaleModCli), unrpyc **v2.0.4**, JPEXS **26.3.0**, Vineflower **1.11.1** (Maven Central),
  `@electron/asar` **4.3.1** (the old `asar` npm package moved to the `@electron` scope).
- Python bytecode: **uncompyle6/decompyle3 only cover up to 3.8**, so the "maintained bytecode decompiler"
  is **PyLingual** (3.6 → 3.15, `uv tool install` from its clone) with **pycdc** as the second opinion.
  pyinstxtractor is maintained (pushed 2026-07).
- Consoles: splat64 **0.50.0** (`pip install splat64[mips]`; N64/PS1/PS2/PSP), decomp-toolkit **1.8.4**
  (GameCube/Wii; splat recommends it for those), N64Recomp (maintained; build from source), XenonRecomp
  (**no releases; build from source**), PS2Recomp (active), objdiff, m2c, decomp-permuter (all active).
- Ghidra loaders: XboxDev/ghidra-xbe (XBE), zeroKilo/XEXLoaderWV (XEX), zeroKilo/N64LoaderWV,
  pedro-javierf/NTRGhidra (NDS), Adubbz/Ghidra-Switch-Loader (NSO/NRO), lab313ru/ghidra_psx_ldr (PS1),
  Cuyler36/Ghidra-GameCube-Loader (DOL/REL). **beardypig/ghidra-emotionengine is archived (2023) →
  replaced by chaoticgd/ghidra-emotionengine-reloaded** (PS2). GhidraGBA has had no push since 2021; GBA
  is plain ARMv4T, which Ghidra handles with a manual raw import at 0x08000000, so the playbook says that
  and lists the loader as optional.
- SDL: latest release **3.4.18** → the platform layer targets **SDL3**.

### Policy decision: encrypted console executables
PS3 SELF, Switch NCA/NSP, retail XEX and PSP EBOOTs are usually encrypted. Decrypting them is a protection
measure in the sense of the hard rules, so `ud scan` reports them as **protected** (a sanctioned stop). The
playbook tells the agent to ask the user for an executable they decrypted themselves from their own console;
the agent never decrypts. Same treatment as Denuvo/SteamStub on PC.

### Core CLI written and exercised on real binaries
- `ud scan` checked on `/usr/bin/ls` (ELF), Windows `notepad.exe` (PE32+) and a .NET Framework exe through WSL.
  **Bug found:** the Rich header picked "VS2008" for notepad because old import-library entries (VS2008
  `Implib900`, 94 objects) outnumber the real toolset. Fix: take the newest *product id* and its highest
  build. Second bug: build numbers repeat across generations (33145 is both inside the VS2013 range and
  VS2022), so the product id now picks the table (>= 0xFD is toolset 14.x). notepad now reads
  "Visual Studio 2022 [build 33145]".
- `ud tools check --route native` on this machine: everything present once `GHIDRA_INSTALL_DIR` points at
  `~/Software/ghidra_12.1.4_PUBLIC` (set only in my own commands; the user's shell config is untouched).

### The worked example, done for real (examples/tinyquest)
- Wrote a small C-style engine ("the original"), built it stripped (`-O1 -fno-inline -s -no-pie`), and ran
  the actual workflow in a scratch decomp repo: `ud init` -> `ud scan` -> `ud tools check` -> Ghidra
  12.1.4 headless with `ud/ghidra/ExportFunctions.java` + `DecompileAll.java` -> `ud funcs import` ->
  reading the decompiler output (kept in the gitignored build/, never committed) -> C++ reconstruction ->
  `ud build` -> `ud run --compare`. Output identical on 7 argument sets (seeds, custom inputs, --render).
- Honest caveat recorded in the example README: the same agent wrote the original, so this demonstrates
  the workflow and tooling, not a blind decompilation.
- `ud build` caught a real compile error in the first build (missing `<initializer_list>`) and printed it
  as file:line: message, as intended.
- pyghidra-mcp: `ud mcp pyghidra --write` output started a working server (MCP `initialize` answered by
  pyghidra-mcp 0.2.7). `search_symbols_by_name(functions_only=True)` returns `{"symbols": [{name, address,
  is_thunk, ...}]}`; `ud funcs import` now reads that shape (`is_thunk` added). Project path made
  repo-relative so the config survives moving the repo.
- **Port 8000 was already taken by the user's own pyghidra-mcp server** (started before this session). I
  sent it two read-only calls by mistake before noticing, then used port 8765 for tests and stopped only my
  own server by exact PID. Not touched otherwise.
- **Footgun found while testing the pre-push hook:** after the hook blocked a commit containing
  `data/tinyquest`, I undid it with `git reset --hard HEAD~1`, which also deleted the (ignored) binary from
  disk because it was tracked in the commit being dropped. The guard's failure message now says to use
  `git rm --cached <file>` and warns about `reset --hard`.
- Public-remote detection verified live: a public GitHub repo and a public GitLab project FAIL, a
  nonexistent/private GitHub repo passes, an unknown host WARNs.

### More tool substitutions found while writing the registry and playbooks
- **unrpa** (Ren'Py archives): last release 2019 -> **rpatool** (Shizmob) in `tools.toml`; unrpyc v2.0.4
  for `.rpyc`.
- **Vineflower**: Maven Central's search API still answered 1.11.1, the GitHub release redirect says
  **1.12.0**; install steps use 1.12.0.
- **Cpp2IL**: the last *tagged* release is 2022.0.7; its README points to development builds
  (`Cpp2IL-net9-<os>-x64.zip`), so the install steps do too.
- **Xenia**: `xenia-project/xenia-canary` is gone (404); the canary builds live at
  `xenia-canary/xenia-canary`.
- Added and checked: kotcrab/ghidra-allegrex (v21.4, PSP), uuksu/RPGMakerDecrypter (v3.0.4),
  XboxDev/extract-xiso, zeroKilo/XEXLoaderWV (12.1.3 matches Ghidra 12.1), XboxDev/ghidra-xbe,
  pyinstxtractor-ng (PyPI 2026.7.3).

### Decisions while writing skills and the remaining commands
- **One playbook per family row of the spec** (11 files). The console row stays one playbook
  (`consoles.md`) with per-console tables: the detection/route/tools differ per console, the method doesn't.
- **Encrypted assets** (RPG Maker MV/MZ `.rpgmvp`, encrypted Godot packs, Unreal AES paks, encrypted IL2CPP
  metadata, encrypted PyInstaller archives) are treated as protections: stop, unless the user supplies a key
  they're entitled to use. Same reasoning as encrypted console executables.
- **`ud run` screenshots on Windows:** universal-modder's `um win shot` uses an ffmpeg build with
  `gfxcapture` that `um win setup` downloads. `ud` uses `PrintWindow(PW_RENDERFULLCONTENT)` from
  PowerShell-embedded C# instead (same delivery style as `um/ps1/*.ps1`), so nothing has to be downloaded
  and the window is found by the PID `ud run` started. Trade-off: some exclusive-fullscreen windows can
  capture black; the skill says to run windowed. Linux: xdotool + ImageMagick on X11, grim on Wayland.
- **`ud run` crash semantics:** only signals (POSIX) and NTSTATUS exception codes (>= 0xC0000000) count as
  crashes; a plain non-zero exit code is the program's answer (the TinyQuest original returns 2 when the
  player dies, which the first version wrongly flagged).
- **`ud publish check` scans the whole history**, not just HEAD (a file deleted in a later commit is still
  pushed), finds renamed copies of `data/` files by git blob hash (only data files whose size matches a
  tracked blob are hashed, so a multi-GB install stays cheap), and matches `data/`, `extracted/`, `ghidra/`
  only at the repo root (a source folder `src/data/` is fine).
- **SDL 3.4's CMake now refuses to configure on Linux when a default backend's dev package is missing**
  (e.g. "Couldn't find dependency package for XCURSOR"). The scaffold therefore prefers an installed SDL3,
  fetches it otherwise, and has an opt-in `UD_SDL_MINIMAL` (dummy/offscreen video only, no GPU/audio
  backends) for CI and headless oracle runs. Verified locally: `ud init --scaffold`,
  `ud build -D CMAKE_DISABLE_FIND_PACKAGE_SDL3=ON -D UD_SDL_MINIMAL=ON`, `ud run -- --headless --frames 3`
  prints "vertical slice ok" with SDL 3.4.18. `tools.toml` lists SDL's Linux build dependencies for users.
- **`ud build`** adds `-A x64` on Windows unless the user passes `-D CMAKE_GENERATOR_PLATFORM=...` (the
  32-bit DLL step of the hybrid route).
- **`kb check`** for decompiled code: a code block with a strong signal (Ghidra types such as `undefined4`,
  `uVar1`/`param_1`-style locals, decompiler banners) or two weaker ones fails; more than 40 distinct
  addresses in a note fails, more than 15 warns; code blocks over 40 lines fail (universal-modder: 150).

### Verification status (end of day)
- `uv run pytest`: 123 tests pass locally on Linux (WSL2, Python 3.12.3, GCC 13.3, CMake 3.28); 1 skipped
  (the Git Bash `cygpath` hook test, Windows only). `uv run ruff check` clean. `ud kb check --index` and
  `scripts/sync_skills.py --check` pass.
- `uv tool install .` into a throwaway tool dir: `ud` runs, packaged data (`tools.toml`, templates, Ghidra
  scripts, the PowerShell helper) is present, `ud init` from the installed tool writes a hook that falls
  back to the tool's own interpreter.
- **Not verified from this session:** anything on Windows. There's no MSVC on this machine, and I don't push
  without being asked, so the Windows jobs in `.github/workflows/test.yml` (tests, the TinyQuest example with
  MSVC, the SDL3 scaffold) have never run. The example's `DECOMP_PLAN.md` keeps its Windows item unchecked
  until that CI job passes.

### Next steps
1. Push (when the user says so) and read the first CI run, especially the Windows jobs.
2. Windows-specific code paths that only CI can exercise: `WinShot.ps1`, `taskkill /T` in `ud run`, the
   pre-push hook under Git for Windows' sh.
3. Once the GitHub repo is public, `ud kb search` outside a clone syncs from it (`hammerill/universal-decompiler`).
