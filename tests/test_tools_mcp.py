"""ud tools check against a mocked PATH, registry consistency, and ud mcp pyghidra config writing."""
from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path

import pytest
from conftest import ud

from ud import mcp, scan, tools


def fake_tool(bindir: Path, name: str, output: str):
    """An executable on PATH that prints `output` (version banners)."""
    bindir.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        (bindir / f"{name}.cmd").write_text(f"@echo off\r\necho {output}\r\n", encoding="utf-8")
    else:
        p = bindir / name
        p.write_text(f"#!/bin/sh\necho '{output}'\n", encoding="utf-8")
        p.chmod(0o755)


@pytest.fixture
def mocked_path(tmp_path, monkeypatch):
    b = tmp_path / "bin"
    monkeypatch.setenv("PATH", str(b))
    if os.name == "nt":
        monkeypatch.setenv("PATHEXT", ".COM;.EXE;.BAT;.CMD")
    for var in ("GHIDRA_INSTALL_DIR", "SDL3_DIR", "ASSETRIPPER_DIR"):
        monkeypatch.delenv(var, raising=False)
    # `paths` probes (e.g. Visual Studio's vswhere.exe on Windows runners) must not see the real machine
    for var in ("ProgramFiles", "ProgramFiles(x86)"):
        monkeypatch.setenv(var, str(tmp_path / "no-program-files"))
    tools.registry.cache_clear()
    return b


def by_id(result):
    return {t["id"]: t for t in result["required"] + result["optional"]}


def test_base_route_all_present(mocked_path):
    fake_tool(mocked_path, "git", "git version 2.47.1")
    fake_tool(mocked_path, "cmake", "cmake version 3.31.6")
    fake_tool(mocked_path, "g++", "g++ (GCC) 14.2.0")
    fake_tool(mocked_path, "python3", "Python 3.12.9")
    fake_tool(mocked_path, "uv", "uv 0.9.0")
    r = tools.check_route("base", "linux")
    t = by_id(r)
    assert r["ok"] and r["missing"] == []
    assert t["cmake"]["version"] == "3.31.6" and t["python"]["version"] == "3.12.9" and t["cxx"]["ok"]
    assert t["ninja"]["found"] is False                     # optional and absent: fine


def test_old_version_and_missing_tools(mocked_path):
    fake_tool(mocked_path, "git", "git version 2.47.1")
    fake_tool(mocked_path, "cmake", "cmake version 3.10.2")
    r = tools.check_route("base", "linux")
    t = by_id(r)
    assert not r["ok"]
    assert t["cmake"]["found"] and not t["cmake"]["ok"] and "older than" in t["cmake"]["note"]
    assert set(r["missing"]) >= {"cmake", "cxx", "python", "uv"}
    text = tools.format_check(r)
    assert "MISSING" in text and "never installs" in text and "sudo apt install cmake" in text
    assert "(windows: winget install --id Kitware.CMake -e" in text


def test_macos_gets_its_own_install_steps(mocked_path):
    r = tools.check_route("native", "macos")
    t = by_id(r)
    assert t["screenshot-x11"]["available"] is False and t["x64dbg"]["available"] is False
    assert t["gdb"]["available"] is True                   # LLDB on macOS
    text = tools.format_check(r)
    assert "brew install cmake" in text and "xcode-select --install" in text and "sudo apt" not in text
    assert "(windows: winget install --id Kitware.CMake -e" in text


def test_env_dir_tool_and_version_file(mocked_path, tmp_path, monkeypatch):
    g = tmp_path / "ghidra_12.1.4_PUBLIC"
    (g / "support").mkdir(parents=True)
    (g / "Ghidra").mkdir()
    (g / "ghidraRun").write_text("#!/bin/sh\n", encoding="utf-8")
    (g / "Ghidra" / "application.properties").write_text("application.name=Ghidra\napplication.version=12.1.4\n", encoding="utf-8")
    monkeypatch.setenv("GHIDRA_INSTALL_DIR", str(g))
    t = tools.check_tool("ghidra", tools.registry()["tools"]["ghidra"], "linux")
    assert t["ok"] and t["version"] == "12.1.4"
    (g / "Ghidra" / "application.properties").write_text("application.version=11.4\n", encoding="utf-8")
    t = tools.check_tool("ghidra", tools.registry()["tools"]["ghidra"], "linux")
    assert t["found"] and not t["ok"]
    monkeypatch.setenv("GHIDRA_INSTALL_DIR", str(tmp_path / "nowhere"))
    t = tools.check_tool("ghidra", tools.registry()["tools"]["ghidra"], "linux")
    assert not t["found"] and "doesn't exist" in t["note"]


def test_platform_specific_tool(mocked_path):
    t = tools.check_tool("fmodel", tools.registry()["tools"]["fmodel"], "linux")
    assert t["available"] is False and not t["ok"]
    r = tools.check_route("unreal", "linux")
    assert "fmodel" not in r["missing"]


def test_cli_exit_codes(mocked_path):
    env = {"PATH": os.environ["PATH"]}
    r = ud("tools", "check", "--route", "base", "--json", env=env)
    assert r.returncode == 1 and json.loads(r.stdout)["missing"]
    assert ud("tools", "check", "--route", "no-such-route", env=env).returncode == 2
    assert ud("tools", "list", "--json", env=env).returncode == 0


def test_registry_is_consistent():
    reg = tomllib.loads(tools.REGISTRY.read_text(encoding="utf-8"))
    for rid, route in reg["routes"].items():
        for tid in route["required"] + route.get("optional", []):
            assert tid in reg["tools"], f"route {rid} names unknown tool {tid}"
    for tid, spec in reg["tools"].items():
        assert spec.get("name") and spec.get("homepage"), tid
        for osk in spec.get("platforms", ["windows", "linux", "macos"]):
            assert spec.get("install", {}).get(osk), f"{tid}: no install steps for {osk}"
        assert any(k in spec for k in ("bin", "env", "paths", "pkgconfig", "python_module", "ghidra_extension")), tid
    # every route ud scan can suggest exists in the registry
    for fam in scan.FAMILIES:
        for r in scan.routes_for(fam, None):
            assert r["tools_route"] in reg["routes"], (fam, r["tools_route"])


# --------------------------------------------------------------------------- mcp


class A:
    def __init__(self, **kw):
        self.agent, self.write, self.transport, self.binary = None, False, "http", None
        self.project_path, self.ghidra_dir, self.host, self.port, self.json = "ghidra", None, "127.0.0.1", 8000, True
        self.__dict__.update(kw)


def test_mcp_writes_every_agent_config(repo, tmp_path, monkeypatch, capsys):
    ghidra = tmp_path / "ghidra_12.1.4_PUBLIC"
    ghidra.mkdir()
    (repo / "data").mkdir()
    (repo / "data" / "game.exe").write_bytes(b"MZ")
    for agent in mcp.AGENTS:
        rc = mcp.pyghidra(A(agent=agent, write=True, ghidra_dir=str(ghidra)))
        out = json.loads(capsys.readouterr().out)
        assert mcp.AGENTS[agent] in out["written"]
        assert rc in (0, 1)                                   # 1 only when pyghidra-mcp isn't installed here
    assert json.loads((repo / ".mcp.json").read_text())["mcpServers"]["pyghidra-mcp"] == {"type": "http", "url": "http://127.0.0.1:8000/mcp"}
    assert json.loads((repo / ".vscode" / "mcp.json").read_text())["servers"]["pyghidra-mcp"]["type"] == "http"
    assert json.loads((repo / ".gemini" / "settings.json").read_text())["mcpServers"]["pyghidra-mcp"]["httpUrl"].endswith("/mcp")
    assert json.loads((repo / "opencode.json").read_text())["mcp"]["pyghidra-mcp"]["type"] == "remote"
    assert tomllib.loads((repo / ".codex" / "config.toml").read_text())["mcp_servers"]["pyghidra-mcp"]["url"].endswith("/mcp")
    script = (repo / "tools" / "start-pyghidra-mcp.sh").read_text()
    assert "--transport streamable-http" in script and "--project-path ghidra" in script and "data/game.exe" in script


def test_mcp_merge_keeps_other_servers_and_stdio(repo, tmp_path, capsys):
    ghidra = tmp_path / "g"
    ghidra.mkdir()
    (repo / ".mcp.json").write_text(json.dumps({"mcpServers": {"other": {"type": "http", "url": "http://x"}}}))
    (repo / ".codex").mkdir()
    (repo / ".codex" / "config.toml").write_text('model = "x"\n\n[mcp_servers.pyghidra-mcp]\nurl = "old"\n\n[mcp_servers.other]\nurl = "y"\n')
    mcp.pyghidra(A(agent="claude", write=True, ghidra_dir=str(ghidra), transport="stdio", binary="data/a.exe"))
    mcp.pyghidra(A(agent="codex", write=True, ghidra_dir=str(ghidra), port=8765))
    capsys.readouterr()
    cfg = json.loads((repo / ".mcp.json").read_text())["mcpServers"]
    assert "other" in cfg and cfg["pyghidra-mcp"]["type"] == "stdio"
    assert cfg["pyghidra-mcp"]["env"]["GHIDRA_INSTALL_DIR"] == str(ghidra) and "--transport" in cfg["pyghidra-mcp"]["args"]
    codex = tomllib.loads((repo / ".codex" / "config.toml").read_text())
    assert codex["model"] == "x" and codex["mcp_servers"]["other"]["url"] == "y"
    assert codex["mcp_servers"]["pyghidra-mcp"]["url"] == "http://127.0.0.1:8765/mcp"


def test_mcp_without_ghidra_is_a_problem(repo, monkeypatch, capsys):
    monkeypatch.delenv("GHIDRA_INSTALL_DIR", raising=False)
    rc = mcp.pyghidra(A(agent="claude", write=True))
    out = json.loads(capsys.readouterr().out)
    assert rc == 1 and out["written"] == [] and any("GHIDRA_INSTALL_DIR" in p for p in out["problems"])
    assert not (repo / ".mcp.json").exists()


def test_mcp_print_all_agents(repo, tmp_path):
    r = ud("mcp", "pyghidra", "--ghidra-dir", str(tmp_path), "--binary", "data/x.exe", cwd=repo)
    for agent, f in mcp.AGENTS.items():
        assert f"--- {agent}: {f}" in r.stdout
    assert ud("mcp", "pyghidra", "--write", cwd=repo).returncode == 2       # --write needs --agent



def test_tools_show(mocked_path):
    fake_tool(mocked_path, "cmake", "cmake version 3.31.6")
    r = ud("tools", "show", "cmake", "--json", env={"PATH": os.environ["PATH"]})
    t = json.loads(r.stdout)
    assert r.returncode == 0 and t["version"] == "3.31.6" and t["install"]["windows"] and t["install"]["linux"] and t["install"]["macos"]
    assert ud("tools", "show", "ghidra", env={"PATH": os.environ["PATH"]}).returncode == 1     # not installed in the mock
    assert ud("tools", "show", "nope", env={"PATH": os.environ["PATH"]}).returncode == 2
