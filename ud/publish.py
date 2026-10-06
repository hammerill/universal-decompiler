"""Refuse to publish a decomp repo. Run by the pre-push hook that `ud init` installs, and by hand.

    ud publish check                    # this repo: tracked files (whole history) + every remote
    ud publish check --remote origin --url git@github.com:me/game-decomp.git    # what the hook passes
    ud publish check --offline --json   # skip the network checks (they become warnings)

FAIL  anything under data/ (the original and its install), files byte-identical to a file in data/,
      binaries and game containers (.exe .dll .so .xbe .xex .self .nso .iso .z64 .gba .pak .pck .assets
      .uasset .rpa .swf ...), Ghidra projects (*.gpr, *.rep: they embed the binary), extracted-asset folders,
      any blob over 5 MiB, in any commit reachable from any ref (a file deleted later is still pushed),
      and any remote that is a public repository (GitHub/GitLab/Codeberg/Bitbucket: `gh` when available,
      otherwise an unauthenticated API request: if anyone can read it, it's public)
WARN  blobs over 1 MiB, archives (.zip/.7z), remotes on hosts we can't check, network failures

The decompilation output is for local management only. re3 was taken down by DMCA in 2021 despite shipping
no assets. Exceptions for your own small files: [publish] allow = ["glob", ...] in ud.toml.
Some patterns are derived from universal-modder's um/publish.py (MIT, Copyright (c) 2026 Rehan and
universal-modder contributors).
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from ud.common import OK, PROBLEM, emit_json, git, load_config, repo_root

SECRET_PATTERNS = [
    ("Anthropic key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("OpenAI key", re.compile(r"\bsk-(?:(?:proj|svcacct|admin)-[A-Za-z0-9_\-]{32,}|[A-Za-z0-9]{32,})")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{60,})")),
    ("AWS key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
]
DECOMP_PATTERNS = [
    ("Ghidra auto-name", re.compile(r"\b(?:FUN|DAT|LAB|PTR|SUB|UNK)_[0-9a-fA-F]{6,}\b")),
    ("IDA auto-name", re.compile(r"\b(?:sub|loc|unk|off|dword|qword|byte|word)_[0-9A-F]{5,}\b")),
    ("Ghidra decompiler types", re.compile(r"\bundefined[1248]?\b|\bin_stack_[0-9a-f]+\b|\bextraout_[A-Z]+\b|\bunaff_[A-Za-z0-9]+\b")),
    ("Ghidra/IDA locals", re.compile(r"\b(?:[ipu]Var|uVar|lVar|bVar|cVar|sVar|pcVar|puVar|piVar|ppVar|auVar)\d+\b|\b(?:local|param)_[0-9a-f]{1,4}\b|\bv\d+\s*=\s*")),
    ("decompiler banner", re.compile(r"/\*\s*WARNING: |Decompiled with|JetBrains decompiler|^\s*//\s*ILSpy|// Decompiled by", re.M)),
]
BINARY_EXT = {
    ".exe", ".dll", ".so", ".dylib", ".sys", ".ocx", ".xbe", ".xex", ".elf", ".self", ".sprx", ".prx", ".nso", ".nro", ".nsp",
    ".xci", ".nca", ".iso", ".cso", ".gcm", ".rvz", ".wia", ".gcz", ".wbfs", ".z64", ".n64", ".v64", ".gba", ".nds", ".3ds",
    ".dol", ".rel", ".pbp", ".cue", ".chd", ".pak", ".pck", ".assets", ".resource", ".resS", ".unity3d", ".bundle", ".upk",
    ".uasset", ".uexp", ".ubulk", ".utoc", ".ucas", ".rpa", ".rgssad", ".rgss2a", ".rgss3a", ".swf", ".xnb", ".vpk", ".bsa",
    ".ba2", ".wad", ".pk3", ".pk4", ".bik", ".bk2", ".xwb", ".xsb", ".fsb", ".bnk", ".wem", ".apk", ".ipa", ".msi", ".cab",
    ".gpr", ".gzf", ".jar", ".love", ".asar", ".win", ".data", ".rpf", ".img", ".txd", ".dff", ".ifp", ".col",
}
ARCHIVE_EXT = {".zip", ".7z", ".rar", ".tar", ".gz", ".xz", ".zst", ".bz2", ".pdb"}
FAIL_DIRS = ["data/", "extracted/", "assets/extracted/", "ghidra/", "pyghidra_mcp_projects/", "dump/", "dumps/"]
FAIL_BYTES, WARN_BYTES = 5 << 20, 1 << 20


# --------------------------------------------------------------------------- tracked content


def history_blobs(root: Path) -> list[tuple[str, int, str]]:
    """(path, size, sha) for every blob reachable from any ref, plus the index."""
    out: dict[tuple[str, str], int] = {}
    revs = git(["rev-list", "--objects", "--all"], cwd=root)
    pairs = []
    for line in revs.stdout.splitlines():
        sha, _, path = line.partition(" ")
        if path:
            pairs.append((sha, path))
    idx = git(["ls-files", "-s", "-z"], cwd=root)
    for ent in idx.stdout.split("\0"):
        if not ent:
            continue
        meta, _, path = ent.partition("\t")
        parts = meta.split()
        if len(parts) >= 2:
            pairs.append((parts[1], path))
    if not pairs:
        return []
    p = subprocess.run(["git", "cat-file", "--batch-check=%(objecttype) %(objectname) %(objectsize)"], cwd=root,
                       input="\n".join(s for s, _ in pairs) + "\n", capture_output=True, text=True)
    types = {}
    for line in p.stdout.splitlines():
        parts = line.split()
        if len(parts) == 3:
            types[parts[1]] = (parts[0], int(parts[2]))
    for sha, path in pairs:
        t = types.get(sha)
        if t and t[0] == "blob":
            out[(path, sha)] = t[1]
    return [(path, size, sha) for (path, sha), size in sorted(out.items())]


def data_blob_hashes(root: Path, data_dir: Path, sizes: set[int]) -> dict[str, str]:
    """git blob sha -> data path, only for data files whose size matches a tracked blob (cheap on GB installs)."""
    cands = []
    if data_dir.is_dir():
        for p in data_dir.rglob("*"):
            try:
                if p.is_file() and p.stat().st_size in sizes:
                    cands.append(p)
            except OSError:
                pass
    if not cands:
        return {}
    r = subprocess.run(["git", "hash-object", "--no-filters", "--stdin-paths"], cwd=root, input="\n".join(map(str, cands)) + "\n",
                       capture_output=True, text=True)
    return {sha: str(p.relative_to(root).as_posix()) for sha, p in zip(r.stdout.split(), cands, strict=False)}


def check_files(root: Path, cfg: dict) -> tuple[list[str], list[str], int]:
    pub = cfg.get("publish", {})
    allow = pub.get("allow", [])
    data = (cfg.get("project", {}).get("data_dir") or "data").strip("/") + "/"
    fail_dirs = sorted(set(FAIL_DIRS + [data] + [d.strip("/") + "/" for d in pub.get("asset_dirs", [])]))
    fail_bytes = int(pub.get("max_file_mb", 5) * (1 << 20)) if "max_file_mb" in pub else FAIL_BYTES
    blobs = history_blobs(root)
    fails, warns = [], []
    flagged = set()
    current = set(git(["ls-files", "-z"], cwd=root).stdout.split("\0"))

    def where(path):
        return "" if path in current else " (in history: deleted later, but still pushed)"

    for path, size, _sha in blobs:
        if any(fnmatch.fnmatch(path, a) for a in allow):
            continue
        low = path.lower()
        ext = os.path.splitext(low)[1]
        reason = None
        if any(low.startswith(d.lower()) for d in fail_dirs):          # repo-root folders only (src/data/*.cpp is fine)
            reason = "original data / extracted assets / Ghidra project"
        elif ext in BINARY_EXT or low.endswith(".rep") or "/.rep/" in low or re.search(r"\.rep/", low):
            reason = f"binary or game container ({ext or 'Ghidra .rep'})"
        elif size > fail_bytes:
            reason = f"large file ({size / (1 << 20):.1f} MiB)"
        if reason:
            if (path, reason) not in flagged:
                flagged.add((path, reason))
                fails.append(f"{path}: {reason}{where(path)}")
            continue
        if size > WARN_BYTES:
            warns.append(f"{path}: {size / (1 << 20):.1f} MiB{where(path)}")
        elif ext in ARCHIVE_EXT:
            warns.append(f"{path}: archive/debug file, make sure it holds nothing from the original{where(path)}")
    same = data_blob_hashes(root, root / data.rstrip("/"), {s for _, s, _ in blobs if s >= 64})
    for path, _size, sha in blobs:
        if sha in same and not any(fnmatch.fnmatch(path, a) for a in allow) and not path.lower().startswith(data.lower()):
            fails.append(f"{path}: byte-identical to {same[sha]} (a file from the original){where(path)}")
    # decompiler dumps and secrets in tracked text (current tree only)
    for path in sorted(current):
        if not path or os.path.splitext(path)[1].lower() not in {".c", ".cpp", ".cc", ".h", ".hpp", ".cs", ".py", ".md", ".txt", ".toml", ".json", ".env"}:
            continue
        try:
            txt = (root / path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for label, rx in SECRET_PATTERNS:
            if rx.search(txt):
                fails.append(f"{path}: {label}")
    return fails, warns, len(blobs)


# --------------------------------------------------------------------------- remotes

def parse_remote(url: str) -> tuple[str, str] | None:
    """-> (host, owner/repo) for hosted remotes; None for local paths."""
    u = url.strip()
    m = re.match(r"^(?:ssh://)?[\w.\-]+@([\w.\-]+)(?::\d+)?[:/](.+?)(?:\.git)?/?$", u)
    if not m:
        m = re.match(r"^(?:https?|git|ssh)://(?:[^@/]+@)?([\w.\-]+)(?::\d+)?/(.+?)(?:\.git)?/?$", u)
    if not m:
        return None
    return m.group(1).lower(), m.group(2)


def _get(url: str, timeout: float = 15) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": "universal-decompiler", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(1 << 20)
    except urllib.error.HTTPError as e:
        return e.code, b""


def is_public(url: str) -> tuple[bool | None, str]:
    """(True public / False not publicly readable / None unknown, how we know)."""
    pr = parse_remote(url)
    if pr is None:
        return False, "local path"
    host, path = pr
    try:
        if host == "github.com" or host.endswith(".github.com"):
            if shutil.which("gh"):
                r = subprocess.run(["gh", "repo", "view", path, "--json", "visibility", "-q", ".visibility"], capture_output=True, text=True, timeout=30)
                vis = r.stdout.strip().upper()
                if r.returncode == 0 and vis:
                    return vis == "PUBLIC", f"gh: {vis.lower()}"
            code, body = _get(f"https://api.github.com/repos/{path}")
            if code == 200:
                return not json.loads(body or b"{}").get("private", False), "GitHub API (unauthenticated) can read it"
            if code == 404:
                return False, "GitHub API: not publicly readable"
            code, _ = _get(f"https://github.com/{path}")
            if code == 200:
                return True, "github.com page is publicly readable"
            if code == 404:
                return False, "github.com page: not publicly readable"
            return None, f"GitHub answered {code}"
        if "gitlab" in host:
            code, body = _get(f"https://{host}/api/v4/projects/{urllib.parse.quote(path, safe='')}")
            if code == 200:
                vis = json.loads(body or b"{}").get("visibility", "public")
                return vis == "public", f"GitLab API: {vis}"
            if code in (401, 403, 404):
                return False, "GitLab API: not publicly readable"
            return None, f"GitLab answered {code}"
        if host in ("codeberg.org",) or "gitea" in host or "forgejo" in host:
            code, body = _get(f"https://{host}/api/v1/repos/{path}")
            if code == 200:
                return not json.loads(body or b"{}").get("private", False), "Gitea/Forgejo API can read it"
            if code in (401, 403, 404):
                return False, "Gitea/Forgejo API: not publicly readable"
            return None, f"{host} answered {code}"
        if host == "bitbucket.org":
            code, _ = _get(f"https://api.bitbucket.org/2.0/repositories/{path}")
            if code == 200:
                return True, "Bitbucket API can read it"
            if code in (401, 403, 404):
                return False, "Bitbucket API: not publicly readable"
            return None, f"Bitbucket answered {code}"
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        return None, f"couldn't check ({e.__class__.__name__}: {e})"
    return None, f"unknown host {host}: can't verify visibility"


def remotes(root: Path) -> list[tuple[str, str]]:
    out, seen = [], set()
    for line in git(["remote", "-v"], cwd=root).stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[2] == "(push)" and (parts[0], parts[1]) not in seen:
            seen.add((parts[0], parts[1]))
            out.append((parts[0], parts[1]))
    return out


def check(path: str | None = None, remote: str | None = None, url: str | None = None, offline: bool = False) -> dict:
    root = repo_root(path)
    cfg = load_config(root)
    fails, warns, n = check_files(root, cfg)
    offline = offline or bool(os.environ.get("UD_PUBLISH_OFFLINE"))
    targets = [(remote or "(push target)", url)] if url else remotes(root)
    strict = cfg.get("publish", {}).get("unverifiable", "warn") == "fail"
    rem = []
    for name, u in targets:
        if offline:
            pub, how = None, "offline: not checked"
        else:
            pub, how = is_public(u)
        rem.append(dict(name=name, url=u, public=pub, how=how))
        if pub:
            fails.append(f"remote {name} ({u}) is a PUBLIC repository ({how}): a decomp repo must stay private")
        elif pub is None:
            (fails if strict and not offline else warns).append(f"remote {name} ({u}): visibility unknown ({how})")
    return dict(repo=str(root), ok=not fails, fails=fails, warnings=warns, remotes=rem, blobs_checked=n)


def main(a):
    r = check(a.path, a.remote, a.url, a.offline)
    if a.json:
        emit_json(r)
    else:
        for x in r["fails"]:
            print("FAIL ", x)
        for x in r["warnings"]:
            print("WARN ", x)
        print(f"{'FAIL' if r['fails'] else 'PASS'}: {r['blobs_checked']} blobs in history, {len(r['remotes'])} remote(s) checked")
        if r["fails"]:
            print("Nothing from the original (binary, install, extracted assets) may be committed, and the decomp repo must not "
                  "go to a public remote.\n"
                  "  Untrack a file but keep your copy:  git rm --cached <file>  (then commit; `git reset --hard` would delete it from disk)\n"
                  "  Already in older commits:           rewrite them (e.g. git filter-repo --invert-paths --path <file>) before pushing\n"
                  "  Public remote:                      make it private, or remove it (git remote remove <name>)")
    return OK if r["ok"] else PROBLEM


def register(sub):
    import argparse
    p = sub.add_parser("publish", help="refuse to publish: tracked binaries/assets, public remotes (pre-push hook)",
                       description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cs = p.add_subparsers(dest="cmd", metavar="<cmd>")
    q = cs.add_parser("check", help="check the repo (and its remotes)", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    q.add_argument("path", nargs="?", help="a path inside the repo (default: cwd)")
    q.add_argument("--remote", help="remote name (the pre-push hook passes it)")
    q.add_argument("--url", help="remote URL to check instead of all configured remotes")
    q.add_argument("--offline", action="store_true", help="skip the network visibility checks (they become warnings)")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=main)
