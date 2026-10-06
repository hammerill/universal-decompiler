"""Repository checks: layout, manifests, skill copies in sync, playbook template, help screens, PATH hook.
The skill-copy and PATH-hook tests are derived from universal-modder's tests/test_um.py
(MIT, Copyright (c) 2026 Rehan and universal-modder contributors)."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

import pytest
from conftest import ROOT, ud

from ud.cli import GROUPS
from ud.scan import FAMILIES

LAYOUT = ["AGENTS.md", "CLAUDE.md", "GEMINI.md", "README.md", "CONTRIBUTING.md", "LICENSE", "NOTICE", "DEVLOG.md", "pyproject.toml",
          "bin/ud", "hooks/hooks.json", "hooks/add-to-path.sh", ".claude-plugin/plugin.json", ".claude-plugin/marketplace.json",
          ".codex-plugin/plugin.json", ".cursor-plugin/plugin.json", "gemini-extension.json", "opencode.json", "plugin.json",
          "knowledge/INDEX.md", "knowledge/TEMPLATE.md", "examples/tinyquest/README.md", ".github/workflows/test.yml",
          "ud/tools.toml", "scripts/sync_skills.py"]
SKILLS = ["decompile-any-binary", "binary-recon", "reverse-engineering", "cpp-reconstruction", "asset-extraction", "verify-and-run",
          "share-field-notes"]
PLAYBOOK_SECTIONS = ["detection signals", "route", "required tools", "deliverable shape", "known limits", "verification approach"]


def test_layout():
    missing = [p for p in LAYOUT if not (ROOT / p).exists()]
    assert not missing, missing
    assert not (ROOT / "src").exists(), "the package lives in ud/, not src/"
    assert not any((ROOT / f).exists() for f in (".mcp.json", ".cursor/mcp.json", ".vscode/mcp.json", ".codex/config.toml")), \
        "no MCP server of our own: no MCP config in this repo"


def test_skill_copies_match():
    # .agents/skills and .claude/skills are real copies of skills/ (Windows clones turn symlinks into text files)
    def tree(d):
        return {p.relative_to(d).as_posix(): p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file()}
    src = tree(ROOT / "skills")
    for copy in (".agents/skills", ".claude/skills"):
        assert not (ROOT / copy).is_symlink(), f"{copy} must be a folder, not a symlink"
        assert tree(ROOT / copy) == src, f"{copy} differs from skills/: python scripts/sync_skills.py"
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "sync_skills.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


def test_skills_have_frontmatter():
    for name in SKILLS:
        text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        m = re.match(r"^---\nname: (.+)\ndescription: (.+?)\n---\n", text, re.S)
        assert m and m.group(1) == name and len(m.group(2)) > 100, name
    main = (ROOT / "skills" / "decompile-any-binary" / "SKILL.md").read_text(encoding="utf-8")
    for heading in ("## Your tools", "## The loop", "## Hard rules", "## References"):
        assert heading in main
    for step in range(12):
        assert re.search(rf"^### {step}\. ", main, re.M), f"loop step {step}"
    for ref in ("safety.md", "case-studies.md", "cpp-port.md", "platform-layer.md"):
        assert (ROOT / "skills" / "decompile-any-binary" / "references" / ref).exists(), ref


def test_every_family_has_a_playbook_following_the_template():
    engines = ROOT / "skills" / "decompile-any-binary" / "references" / "engines"
    for fam, (_, playbook, _) in FAMILIES.items():
        p = engines / playbook
        assert p.exists(), (fam, playbook)
        heads = [h.lower() for h in re.findall(r"^##\s+(.+)$", p.read_text(encoding="utf-8"), re.M)]
        for s in PLAYBOOK_SECTIONS:
            assert any(h.startswith(s) for h in heads), f"{playbook}: missing '## {s}'"


def test_manifests_point_to_the_skills():
    names = set()
    for f in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json", ".cursor-plugin/plugin.json", "gemini-extension.json", "plugin.json"):
        data = json.loads((ROOT / f).read_text(encoding="utf-8"))
        names.add(data["name"])
        assert "mcpServers" not in data, f"{f}: no MCP server of our own"
    assert names == {"universal-decompiler"}
    assert json.loads((ROOT / ".codex-plugin/plugin.json").read_text())["skills"] == "./skills/"
    assert json.loads((ROOT / "opencode.json").read_text())["skills"]["paths"] == ["skills"]
    assert json.loads((ROOT / "gemini-extension.json").read_text())["contextFileName"] == "AGENTS.md"
    for f in (".claude-plugin/marketplace.json", ".cursor-plugin/marketplace.json"):
        assert json.loads((ROOT / f).read_text())["plugins"][0]["source"] == "./"
    hooks = json.loads((ROOT / "hooks/hooks.json").read_text())
    assert list(hooks["hooks"]) == ["SessionStart"], "SessionStart only: no Stop hook"
    assert "add-to-path.sh" in hooks["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert "add-to-path.sh" in (ROOT / ".claude/settings.json").read_text()
    for f in ("CLAUDE.md", "GEMINI.md"):
        assert (ROOT / f).read_text().startswith("@AGENTS.md")


def test_pyproject():
    import tomllib
    p = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert p["project"]["name"] == "universal-decompiler" and p["project"]["scripts"]["ud"] == "ud.cli:main"
    assert p["project"]["requires-python"] == ">=3.12" and p["project"]["license"] == "MIT"


def test_readme_and_notice_state_origin():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Inspired by universal-modder. Not affiliated with its authors." in readme
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
    assert "Not affiliated with its authors." in notice and "Copyright (c) 2026 Rehan and universal-modder contributors" in notice
    code_section = notice.split("Code (", 1)[1].split("Structure and text", 1)[0]
    for f in re.findall(r"^- ((?:ud|bin|hooks|tests)/[\w./-]+)", code_section, re.M):
        path = ROOT / f
        assert path.exists(), f
        assert "universal-modder" in path.read_text(encoding="utf-8")[:2000], f"{f} must carry the universal-modder notice"
    assert "MIT License" in (ROOT / "LICENSE").read_text()


@pytest.mark.parametrize("group", GROUPS)
def test_help_screens_have_examples(group):
    r = ud(group, "--help")
    assert r.returncode == 0
    assert re.search(rf"^\s+ud {group}\b", r.stdout, re.M), f"`ud {group} --help` shows no examples"


def test_group_without_command_is_usage_error():
    for g in ("tools", "funcs", "publish", "kb", "mcp", "assets"):
        assert ud(g).returncode == 2, g


def test_spec_commands_exist():
    cmds = {"init": [], "scan": [], "tools": ["check"], "mcp": ["pyghidra"], "funcs": ["import", "list", "set", "stats"], "build": [],
            "run": [], "assets": ["check"], "publish": ["check"], "kb": ["search", "show", "new", "check", "index", "sync", "pr"]}
    for g, subs in cmds.items():
        for s in subs:
            assert ud(g, s, "--help").returncode == 0, f"ud {g} {s}"


@pytest.mark.skipif(os.name == "nt" or not shutil.which("bash"), reason="bash hook; the Windows variant needs Git Bash's cygpath")
def test_path_hook_appends_once(tmp_path):
    env_file = tmp_path / "env.sh"
    env = {**os.environ, "CLAUDE_ENV_FILE": str(env_file)}
    hook = ROOT / "hooks" / "add-to-path.sh"
    for _ in range(2):
        subprocess.run(["bash", str(hook), str(ROOT)], env=env, check=True)
    text = env_file.read_text()
    assert text.count("universal-decompiler-path") == 1 and f'{ROOT}/bin:$PATH' in text


@pytest.mark.skipif(not shutil.which("cygpath"), reason="Git Bash / MSYS only")
def test_path_hook_writes_a_posix_root(tmp_path):
    # Claude Code passes ${CLAUDE_PLUGIN_ROOT} as C:/...; written as is, bash splits PATH at the drive colon
    root = tmp_path / "ud root"
    (root / "bin").mkdir(parents=True)
    (root / "bin" / "ud").write_text("#!/bin/sh\n")
    env_file = tmp_path / "env.sh"
    bash = str(shutil.which("bash"))
    subprocess.run([bash, str(ROOT / "hooks" / "add-to-path.sh"), root.as_posix()], env={**os.environ, "CLAUDE_ENV_FILE": str(env_file)}, check=True)
    value = env_file.read_text().split('"')[1]
    prefix = value[:value.index("/bin:$PATH")]
    assert prefix.startswith("/") and ":" not in prefix, value


def test_no_commercial_binaries_in_repo():
    # the example's original is built in CI; nothing executable or packed is committed
    r = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    files = r.stdout.split() if r.returncode == 0 else []
    bad = [f for f in files if re.search(r"\.(exe|dll|so|dylib|xbe|xex|iso|z64|n64|gba|nds|pak|pck|bin|elf)$", f, re.I)]
    assert not bad, bad
