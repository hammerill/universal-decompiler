"""Configure third-party MCP servers in the decomp repo. universal-decompiler ships no MCP server of its own.

    ud mcp pyghidra                          # print the config for every agent + the server start command
    ud mcp pyghidra --agent claude           # just Claude Code (.mcp.json)
    ud mcp pyghidra --agent codex --write    # merge it into .codex/config.toml in this repo
    ud mcp pyghidra --agent vscode --transport stdio --write   # the agent spawns the server itself

Agents and files (project level): claude .mcp.json · codex .codex/config.toml · cursor .cursor/mcp.json ·
gemini .gemini/settings.json · vscode .vscode/mcp.json · opencode opencode.json

Follows the pyghidra-mcp README (checked 2026-10-06, pyghidra-mcp 0.2.7): streamable HTTP is the recommended
transport. Start the server once (`pyghidra-mcp --transport streamable-http --project-path ... <binary>`),
leave it running, and point the agent at http://127.0.0.1:8000/mcp. Claude Code needs "type": "http" (an
entry with only a url is treated as stdio). stdio is for hosts that can't use HTTP. pyghidra-mcp needs
GHIDRA_INSTALL_DIR and JDK 21+; install it with `uv tool install pyghidra-mcp` (`ud tools check --route native`).
The Ghidra project goes to ghidra/ in the repo, which `ud init` gitignores (it embeds the binary).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path

from ud.common import OK, PROBLEM, TEXT, emit_json, load_config, repo_root, usage

AGENTS = {
    "claude": ".mcp.json",
    "codex": ".codex/config.toml",
    "cursor": ".cursor/mcp.json",
    "gemini": ".gemini/settings.json",
    "vscode": ".vscode/mcp.json",
    "opencode": "opencode.json",
}
NAME = "pyghidra-mcp"
PLACEHOLDER = "<path to ghidra_12.1.4_PUBLIC>"


def server_command(binary: str | None, project: Path, name: str, transport: str, host: str, port: int) -> list[str]:
    exe = "pyghidra-mcp" if shutil.which("pyghidra-mcp") else "uvx"
    cmd = [exe] if exe == "pyghidra-mcp" else ["uvx", "pyghidra-mcp"]
    if transport == "http":
        cmd += ["--transport", "streamable-http", "--host", host, "--port", str(port)]
    else:
        cmd += ["--transport", "stdio"]
    cmd += ["--project-path", project.as_posix(), "--project-name", name]
    if binary:
        cmd.append(binary)
    return cmd


def agent_entry(agent: str, transport: str, url: str, cmd: list[str], env: dict) -> dict:
    if transport == "http":
        return {
            "claude": {"type": "http", "url": url},
            "codex": {"url": url},
            "cursor": {"url": url},
            "gemini": {"httpUrl": url},
            "vscode": {"type": "http", "url": url},
            "opencode": {"type": "remote", "url": url, "enabled": True},
        }[agent]
    return {
        "claude": {"type": "stdio", "command": cmd[0], "args": cmd[1:], "env": env},
        "codex": {"command": cmd[0], "args": cmd[1:], "env": env},
        "cursor": {"command": cmd[0], "args": cmd[1:], "env": env},
        "gemini": {"command": cmd[0], "args": cmd[1:], "env": env},
        "vscode": {"type": "stdio", "command": cmd[0], "args": cmd[1:], "env": env},
        "opencode": {"type": "local", "command": cmd, "environment": env, "enabled": True},
    }[agent]


def render(agent: str, entry: dict) -> str:
    if agent == "codex":
        return toml_section(entry)
    top = {"claude": "mcpServers", "cursor": "mcpServers", "gemini": "mcpServers", "vscode": "servers", "opencode": "mcp"}[agent]
    return json.dumps({top: {NAME: entry}}, indent=2)


def _toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{k} = {_toml_value(x)}" for k, x in v.items()) + " }"
    return json.dumps(str(v))


def toml_section(entry: dict) -> str:
    lines = [f"[mcp_servers.{NAME}]"]
    for k, v in entry.items():
        lines.append(f"{k} = {_toml_value(v)}")
    return "\n".join(lines) + "\n"


def write_config(root: Path, agent: str, entry: dict) -> Path:
    path = root / AGENTS[agent]
    path.parent.mkdir(parents=True, exist_ok=True)
    if agent == "codex":
        old = path.read_text(encoding="utf-8") if path.exists() else ""
        # drop an existing [mcp_servers.pyghidra-mcp] table (up to the next table header), then append ours
        old = re.sub(r"(?ms)^\[mcp_servers\.(?:\"?pyghidra-mcp\"?)\]\n.*?(?=^\[|\Z)", "", old).rstrip()
        path.write_text((old + "\n\n" if old else "") + toml_section(entry), **TEXT)
        return path
    top = {"claude": "mcpServers", "cursor": "mcpServers", "gemini": "mcpServers", "vscode": "servers", "opencode": "mcp"}[agent]
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError as e:
            usage(f"{path} is not valid JSON ({e}); fix it or move it away first")
    if agent == "opencode":
        data.setdefault("$schema", "https://opencode.ai/config.json")
    data.setdefault(top, {})[NAME] = entry
    path.write_text(json.dumps(data, indent=2) + "\n", **TEXT)
    return path


def start_scripts(root: Path, cmd: list[str], ghidra: str) -> list[Path]:
    tools = root / "tools"
    tools.mkdir(exist_ok=True)
    sh, ps = tools / "start-pyghidra-mcp.sh", tools / "start-pyghidra-mcp.ps1"
    q = " ".join(f'"{c}"' if " " in c else c for c in cmd)
    sh.write_text(f"#!/bin/sh\n# Starts pyghidra-mcp for this repo (written by `ud mcp pyghidra --write`). Leave it running.\n"
                  f"cd \"$(dirname \"$0\")/..\" || exit 1\n"
                  f"export GHIDRA_INSTALL_DIR=\"${{GHIDRA_INSTALL_DIR:-{ghidra}}}\"\nexec {q}\n", **TEXT)
    sh.chmod(0o755)
    ps.write_text(f"# Starts pyghidra-mcp for this repo (written by `ud mcp pyghidra --write`). Leave it running.\n"
                  f"Set-Location (Join-Path $PSScriptRoot '..')\n"
                  f"if (-not $env:GHIDRA_INSTALL_DIR) {{ $env:GHIDRA_INSTALL_DIR = '{ghidra}' }}\n& {q}\n", encoding="utf-8")
    return [sh, ps]


def guess_binary(root: Path, cfg: dict) -> str | None:
    orig = cfg.get("run", {}).get("original")
    if orig:
        return orig
    data = root / (cfg.get("project", {}).get("data_dir") or "data")
    files = sorted(p for p in data.iterdir() if p.is_file()) if data.is_dir() else []
    exe = [p for p in files if p.suffix.lower() in (".exe", ".xbe", ".xex", ".elf", ".dol", ".nso", ".z64", ".gba", ".nds", ".bin", "")]
    pick = (exe or files)[:1]
    return pick[0].relative_to(root).as_posix() if pick else None


def pyghidra(a) -> int:
    root = repo_root()
    cfg = load_config(root)
    ghidra = a.ghidra_dir or os.environ.get("GHIDRA_INSTALL_DIR") or ""
    binary = a.binary or guess_binary(root, cfg)
    # relative to the repo root, so the config and scripts survive moving the repo (agents start in the repo root)
    project = Path(a.project_path)
    name = re.sub(r"[^A-Za-z0-9_]+", "_", cfg.get("project", {}).get("name") or root.name) or "decomp"
    cmd = server_command(binary, project, name, a.transport, a.host, a.port)
    url = f"http://{a.host}:{a.port}/mcp"
    env = {"GHIDRA_INSTALL_DIR": ghidra or PLACEHOLDER}
    agents = [a.agent] if a.agent else list(AGENTS)
    problems = []
    if not ghidra:
        problems.append("GHIDRA_INSTALL_DIR is not set: install Ghidra 12.1+ and set it (see `ud tools show ghidra`), or pass --ghidra-dir")
    elif not Path(ghidra).is_dir():
        problems.append(f"GHIDRA_INSTALL_DIR={ghidra} doesn't exist")
    if not shutil.which("pyghidra-mcp"):
        problems.append("pyghidra-mcp is not installed: `uv tool install pyghidra-mcp` (the command below falls back to uvx)")
    if not binary:
        problems.append("no binary found in data/: pass --binary data/<file>")
    out: dict = dict(server=dict(transport=a.transport, url=url if a.transport == "http" else None, command=cmd,
                                 env={"GHIDRA_INSTALL_DIR": ghidra or PLACEHOLDER}), agents={}, written=[], problems=problems)
    for ag in agents:
        entry = agent_entry(ag, a.transport, url, cmd, env)
        out["agents"][ag] = dict(file=AGENTS[ag], entry=entry)
    if a.write:
        if not a.agent:
            usage("--write needs --agent (claude, codex, cursor, gemini, vscode or opencode)")
        if not ghidra:
            print("ud: refusing to write a config without GHIDRA_INSTALL_DIR", file=sys.stderr)
            out["written"] = []
        else:
            p = write_config(root, a.agent, out["agents"][a.agent]["entry"])
            out["written"].append(p.relative_to(root).as_posix())
            if a.transport == "http":
                out["written"] += [s.relative_to(root).as_posix() for s in start_scripts(root, cmd, ghidra)]
    if a.json:
        emit_json(out)
    else:
        if a.transport == "http":
            print("1. Start the server (leave it running; first analysis of a big binary takes minutes):")
            print(f"   GHIDRA_INSTALL_DIR=\"{ghidra or PLACEHOLDER}\" " + " ".join(f'"{c}"' if " " in c else c for c in cmd))
            print(f"   It serves {url} (bound to {a.host} only).")
            print("2. Point the agent at it:")
        else:
            print("The agent starts the server itself (stdio). Config:")
        for ag in agents:
            print(f"\n--- {ag}: {AGENTS[ag]}")
            print(render(ag, out["agents"][ag]["entry"]).rstrip())
        if a.agent == "claude" and a.transport == "http":
            print("\n   (or: claude mcp add --transport http pyghidra-mcp " + url + ")")
        for w in out["written"]:
            print(f"wrote {w}")
        if out["written"]:
            print("Restart or reload the agent so it picks up the new MCP server.")
        for pr in problems:
            print(f"PROBLEM: {pr}")
    return PROBLEM if problems else OK


def register(sub):
    import argparse
    p = sub.add_parser("mcp", help="print or write the pyghidra-mcp config for your agent (no MCP server of our own)",
                       description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cs = p.add_subparsers(dest="cmd", metavar="<server>")
    q = cs.add_parser("pyghidra", help="pyghidra-mcp (Ghidra over MCP)", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    q.add_argument("--agent", choices=list(AGENTS))
    q.add_argument("--write", action="store_true", help="merge the config into the agent's file in this repo (needs --agent)")
    q.add_argument("--transport", choices=["http", "stdio"], default="http", help="http (recommended by pyghidra-mcp) or stdio")
    q.add_argument("--binary", help="binary to import (default: ud.toml run.original, else the file in data/)")
    q.add_argument("--project-path", default="ghidra", help="Ghidra project folder in the repo (gitignored by ud init)")
    q.add_argument("--ghidra-dir", help="Ghidra install folder (default: $GHIDRA_INSTALL_DIR)")
    q.add_argument("--host", default="127.0.0.1")
    q.add_argument("--port", type=int, default=8000)
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=pyghidra)
