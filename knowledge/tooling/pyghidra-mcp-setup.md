---
kind: topic
title: "Setting up pyghidra-mcp for an agent in a decomp repo"
family: tooling
tags: [pyghidra-mcp, ghidra, mcp, setup]
tools: ["pyghidra-mcp 0.2.7", "Ghidra 12.1.4", "JDK 25 (Temurin)"]
status: working
agents: ["Claude Code (Opus 5.5)"]
humans: []
date: 2026-10-06
links: ["https://github.com/clearbluejar/pyghidra-mcp"]
---

# Setting up pyghidra-mcp for an agent in a decomp repo

> pyghidra-mcp exposes a headless Ghidra to MCP clients (decompile, xrefs, search, rename, retype). This is
> the setup that worked with `ud mcp pyghidra`, and what to watch for when the agent first talks to it.

## When to use it
Every native route (and the native halves of IL2CPP/Unreal/console work) once `ud tools check --route
native` passes. Without MCP, use Ghidra headless with `ud/ghidra/*.java` instead (see
`ghidra-headless-export-and-decompile.md`).

## How
1. Install: `uv tool install pyghidra-mcp` (0.2.7 at the time of writing, Python >= 3.10), Ghidra 12.1.x
   unzipped with `GHIDRA_INSTALL_DIR` pointing at it, a JDK 21+ (12.1 targets 21; 25 also worked).
2. In the decomp repo: `ud mcp pyghidra --agent <claude|codex|cursor|gemini|vscode|opencode> --write`. It
   writes the agent's project config (Claude Code: `.mcp.json` with `"type": "http"`) and
   `tools/start-pyghidra-mcp.sh` / `.ps1`.
3. Start the server and leave it running: `sh tools/start-pyghidra-mcp.sh`. It runs
   `pyghidra-mcp --transport streamable-http --host 127.0.0.1 --port 8000 --project-path ghidra
   --project-name <repo> data/<binary>`; `ghidra/` is gitignored by `ud init` because the project embeds
   the binary.
4. Reload the agent. First call: `list_project_binaries`, to learn the exact `binary_name`.
5. Inventory: `search_symbols_by_name(binary_name, ".*", functions_only=True, limit=...)`, paginated with
   `offset`, saved as JSON, then `ud funcs import <file>`.

## Gotchas
1. **Tool calls say "Binary /tinyquest not found".** **Cause:** pyghidra-mcp names imported programs with a
   hash suffix (here `/tinyquest-892701`). **Fix:** call `list_project_binaries` first and use the `name`
   it returns.
2. **The server answered but listed no programs at all.** **Cause:** port 8000 was already taken by another
   pyghidra-mcp instance (a different project), and our own server had failed to start. **Fix:** check the
   port before starting (`ss -ltnp | grep 8000`), never touch a server you didn't start, and pass `--port`
   to `ud mcp pyghidra` (it updates both the config and the start script).
3. **Our server exited immediately: "Path 'data/...' does not exist".** **Cause:** pyghidra-mcp validates the
   binary path relative to its working directory, and the binary was missing. **Fix:** the generated start
   script `cd`s to the repo root first; make sure the file is in `data/`.
4. **Claude Code ignored the server.** **Cause:** an entry with only `url` is treated as stdio. **Fix:**
   `"type": "http"` (what `ud mcp` writes), or `claude mcp add --transport http pyghidra-mcp <url>`.
5. **The first tool calls fail right after startup.** **Cause:** the server listens within seconds and
   analyses in the background (asynchronous startup). **Fix:** poll `list_project_binaries` until the
   program shows `"analysis_complete": true`, or start with `--wait-for-analysis`.
6. **`search_symbols_by_name` results have no size.** **Cause:** the symbol search returns name, address,
   type, namespace, refcount and `is_thunk`, not function sizes. **Fix:** `ud funcs import` accepts it
   (thunks are marked skipped); for sizes and byte coverage, also import the headless
   `ExportFunctions.java` output.

## Seen in
`examples/tinyquest/reconstruction/DECOMPLOG.md`.
