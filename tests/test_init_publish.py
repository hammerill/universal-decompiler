"""ud init (idempotence, .gitignore block, pre-push hook) and ud publish check (blocking)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess

import pytest
from conftest import ROOT, git, ud

from ud import init, publish


def test_init_creates_everything_and_is_idempotent(repo):
    (repo / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    r1 = init.init()
    ch = r1["changes"]
    assert ch["data/"] == "created" and ch["DECOMPLOG.md"] == "created" and ch["DECOMP_PLAN.md"] == "created"
    assert ch["ud.toml"] == "created" and ch[".gitignore"] == "updated" and ch["pre-push hook"] == "created"
    gi = (repo / ".gitignore").read_text(encoding="utf-8")
    assert gi.startswith("node_modules/") and "data/" in gi and "*.gpr" in gi and gi.count(init.BEGIN) == 1
    hook = repo / ".git" / "hooks" / "pre-push"
    assert init.HOOK_MARK in hook.read_text(encoding="utf-8")
    if os.name != "nt":
        assert os.access(hook, os.X_OK)
    (repo / "DECOMPLOG.md").write_text("# my journal\n", encoding="utf-8")
    r2 = init.init()
    assert all(v in ("kept", "unchanged") for v in r2["changes"].values()), r2["changes"]
    assert (repo / "DECOMPLOG.md").read_text(encoding="utf-8") == "# my journal\n"
    assert (repo / ".gitignore").read_text(encoding="utf-8") == gi


def test_init_refreshes_a_changed_block_and_keeps_user_lines(repo):
    init.init()
    gi = repo / ".gitignore"
    gi.write_text(gi.read_text(encoding="utf-8").replace("*.gzf\n", "") + "my-notes.txt\n", encoding="utf-8")
    assert init.gitignore(repo) == "updated"
    text = gi.read_text(encoding="utf-8")
    assert "*.gzf" in text and text.rstrip().endswith("my-notes.txt")


def test_init_chains_an_existing_hook(repo):
    hooks = repo / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    (hooks / "pre-push").write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
    assert "pre-push.local" in init.install_hook(repo)
    assert (hooks / "pre-push.local").read_text(encoding="utf-8") == "#!/bin/sh\necho mine\n"
    assert init.HOOK_MARK in (hooks / "pre-push").read_text(encoding="utf-8")
    assert init.install_hook(repo) == "unchanged"


def test_init_outside_git_fails(tmp_path):
    r = ud("init", cwd=tmp_path)
    assert r.returncode == 1 and "git init" in r.stderr


def test_init_scaffold_and_json(repo):
    r = ud("init", "--scaffold", "--json", cwd=repo)
    data = json.loads(r.stdout)
    assert r.returncode == 0 and data["changes"]["CMakeLists.txt"] == "created"
    for f in ("src/main.cpp", "src/platform/platform.h", "src/platform/platform_sdl3.cpp", "src/platform/platform_null.cpp",
              "tools/extract_assets.py", "README.md"):
        assert (repo / f).exists(), f
    assert "release-3.4" in (repo / "CMakeLists.txt").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- publish check


def commit_all(repo, msg="c"):
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", msg)


def test_publish_clean_repo_passes(repo):
    init.init()
    (repo / "data" / "game.exe").write_bytes(b"MZ" + os.urandom(4096))
    (repo / "src").mkdir()
    (repo / "src" / "main.cpp").write_text("// 0x00401000 main\nint main() { return 0; }\n", encoding="utf-8")
    commit_all(repo)
    r = publish.check(str(repo))
    assert r["ok"], r


def test_publish_blocks_tracked_original_and_binaries(repo):
    init.init()
    original = b"MZ" + os.urandom(8000)
    (repo / "data" / "game.exe").write_bytes(original)
    git(repo, "add", "-f", "data/game.exe")
    (repo / "copy_of_game.bin").write_bytes(original)          # renamed copy of a data/ file
    (repo / "tool.dll").write_bytes(b"MZ" + os.urandom(100))
    (repo / "ghidra").mkdir()
    (repo / "ghidra" / "proj.gpr").write_bytes(b"x")
    git(repo, "add", "-f", "tool.dll", "ghidra/proj.gpr", "copy_of_game.bin")
    git(repo, "commit", "-qm", "oops")
    fails = "\n".join(publish.check(str(repo))["fails"])
    assert "data/game.exe" in fails and "tool.dll" in fails and "ghidra/proj.gpr" in fails
    assert "copy_of_game.bin: byte-identical to data/game.exe" in fails


def test_publish_allows_source_folders_named_data(repo):
    init.init()
    (repo / "src" / "data").mkdir(parents=True)
    (repo / "src" / "data" / "levels.cpp").write_text("// 0x00402000 load_levels\n", encoding="utf-8")
    commit_all(repo)
    assert publish.check(str(repo))["ok"]


def test_publish_sees_history_and_large_files(repo):
    init.init()
    (repo / "big.txt").write_bytes(b"a" * (6 << 20))
    commit_all(repo, "big")
    git(repo, "rm", "-q", "--cached", "big.txt")
    (repo / "big.txt").unlink()
    git(repo, "commit", "-qm", "remove")
    fails = publish.check(str(repo))["fails"]
    assert any("big.txt" in f and "history" in f for f in fails)


def test_publish_allow_list(repo):
    init.init()
    (repo / "tests").mkdir()
    (repo / "tests" / "fixture.bin").write_bytes(b"\0" * 64)
    (repo / "tests" / "tiny.exe").write_bytes(b"MZ\0\0")      # *.exe is gitignored by ud init: force it in
    git(repo, "add", "-f", "tests/tiny.exe")
    commit_all(repo)
    assert not publish.check(str(repo))["ok"]
    cfg = (repo / "ud.toml").read_text(encoding="utf-8").replace('allow = []', 'allow = ["tests/*"]')
    (repo / "ud.toml").write_text(cfg, encoding="utf-8")
    assert publish.check(str(repo))["ok"]


def test_publish_blocks_public_remote(repo, monkeypatch):
    init.init()
    commit_all(repo)
    git(repo, "remote", "add", "origin", "https://github.com/someone/public-thing.git")
    git(repo, "remote", "add", "backup", "git@github.com:someone/private-thing.git")
    monkeypatch.delenv("UD_PUBLISH_OFFLINE", raising=False)
    monkeypatch.setattr(publish, "is_public", lambda url: (True, "test: public") if "public-thing" in url else (False, "test: private"))
    r = publish.check(str(repo))
    assert not r["ok"] and len(r["remotes"]) == 2
    assert any("PUBLIC" in f and "origin" in f for f in r["fails"])
    r = publish.check(str(repo), remote="backup", url="git@github.com:someone/private-thing.git")
    assert r["ok"]


def test_publish_offline_warns(repo):
    init.init()
    commit_all(repo)
    git(repo, "remote", "add", "origin", "https://github.com/someone/x.git")
    r = publish.check(str(repo), offline=True)
    assert r["ok"] and any("visibility unknown" in w for w in r["warnings"])


@pytest.mark.parametrize("url,host,path", [
    ("git@github.com:me/repo.git", "github.com", "me/repo"),
    ("https://github.com/me/repo", "github.com", "me/repo"),
    ("ssh://git@gitlab.com:2222/group/sub/repo.git", "gitlab.com", "group/sub/repo"),
    ("https://user@codeberg.org/me/repo.git", "codeberg.org", "me/repo"),
])
def test_parse_remote(url, host, path):
    assert publish.parse_remote(url) == (host, path)


def test_parse_remote_local_paths():
    assert publish.parse_remote("/srv/git/repo.git") is None
    assert publish.is_public("../remote.git") == (False, "local path")


def test_publish_secret_in_tracked_file(repo):
    init.init()
    (repo / "notes.md").write_text("token ghp_" + "a" * 36 + "\n", encoding="utf-8")
    commit_all(repo)
    assert any("GitHub token" in f for f in publish.check(str(repo))["fails"])


@pytest.mark.skipif(not shutil.which("uv") and not shutil.which("ud"), reason="the hook needs ud or uv on PATH")
def test_pre_push_hook_blocks_a_real_push(repo, tmp_path):
    init.init()
    commit_all(repo, "init")
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    git(repo, "remote", "add", "origin", str(remote))
    env = {**os.environ, "UD_PUBLISH_OFFLINE": "1", "PATH": str(ROOT / "bin") + os.pathsep + os.environ["PATH"]}
    ok = subprocess.run(["git", "push", "-q", "origin", "HEAD:main"], cwd=repo, capture_output=True, text=True, env=env)
    assert ok.returncode == 0, ok.stderr
    (repo / "data" / "game.exe").write_bytes(b"MZ" + os.urandom(2000))
    git(repo, "add", "-f", "data/game.exe")
    git(repo, "commit", "-qm", "oops")
    bad = subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=repo, capture_output=True, text=True, env=env)
    assert bad.returncode != 0
    assert "blocked by ud publish check" in bad.stderr + bad.stdout
