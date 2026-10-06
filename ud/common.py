"""Small helpers shared by the subcommands: platform checks, WSL paths, git, subprocess, output, exit codes.

Derived from universal-modder's um/common.py (MIT, Copyright (c) 2026 Rehan and universal-modder contributors).
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

OK, PROBLEM, USAGE = 0, 1, 2
# Text files we write are UTF-8 with \n line ends on every OS (Windows would otherwise use its ANSI code page).
TEXT = {"encoding": "utf-8", "newline": "\n"}


def is_windows() -> bool:
    return os.name == "nt"


def is_mac() -> bool:
    return sys.platform == "darwin"


def is_wsl() -> bool:
    if sys.platform != "linux":
        return False
    return "microsoft" in platform.release().lower() or os.path.exists("/proc/sys/fs/binfmt_misc/WSLInterop")


def os_key() -> str:
    """windows | linux | macos: the key used for per-OS install steps in tools.toml."""
    return "windows" if is_windows() else "macos" if is_mac() else "linux"


def ps_exe() -> str:
    """Windows PowerShell. Falls back to its full path: an agent's PATH often lacks System32\\WindowsPowerShell\\v1.0."""
    name = "powershell.exe" if is_wsl() else "powershell"
    found = shutil.which(name)
    if found:
        return found
    if is_wsl():
        full = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
    else:
        full = os.path.join(os.environ.get("SystemRoot") or r"C:\Windows", "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    return full if os.path.exists(full) else name


def to_win(path: str | Path) -> str:
    """/mnt/c/Games/x -> C:\\Games\\x (WSL); paths that are already Windows paths pass through."""
    p = str(path)
    if len(p) > 1 and p[1] == ":":
        return p
    if p.startswith("/mnt/") and len(p) > 6 and p[6] == "/" and p[5].isalpha():
        return p[5].upper() + ":\\" + p[7:].replace("/", "\\")
    if is_wsl() and shutil.which("wslpath"):
        return subprocess.run(["wslpath", "-w", p], capture_output=True, text=True).stdout.strip()
    return p


def to_posix(path: str | Path) -> str:
    """C:\\Games\\x -> /mnt/c/Games/x under WSL; unchanged elsewhere."""
    p = str(path)
    if is_wsl() and len(p) > 1 and p[1] == ":":
        return "/mnt/" + p[0].lower() + p[2:].replace("\\", "/")
    return p


def data_dir() -> Path:
    """Per-user state (the knowledge-base cache). Override with UD_HOME."""
    d = Path(os.environ.get("UD_HOME", Path.home() / ".universal-decompiler"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def die(msg: str, code: int = PROBLEM) -> NoReturn:
    print(f"ud: {msg}", file=sys.stderr)
    sys.exit(code)


def usage(msg: str) -> NoReturn:
    die(msg, USAGE)


def emit_json(obj):
    print(json.dumps(obj, indent=2, default=str, ensure_ascii=False))


def git(args: list[str], cwd: str | Path | None = None, check: bool = False) -> subprocess.CompletedProcess:
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        die("git is not installed or not on PATH")
    if check and r.returncode:
        die(f"git {' '.join(args[:3])} failed: {(r.stderr or r.stdout).strip()[-800:]}")
    return r


def find_repo(start: str | Path | None = None) -> Path | None:
    """Top of the git work tree that contains `start` (default: cwd), or None."""
    r = git(["rev-parse", "--show-toplevel"], cwd=start or Path.cwd())
    return Path(r.stdout.strip()) if r.returncode == 0 else None


def repo_root(start: str | Path | None = None) -> Path:
    """Like find_repo, but a missing repo ends the command with instructions."""
    root = find_repo(start)
    if root is None:
        die("not inside a git repository: create the decomp folder, run `git init` there, then try again")
    return root


def load_config(root: Path) -> dict:
    """ud.toml at the decomp repo root (written by `ud init`); {} if absent."""
    import tomllib
    p = root / "ud.toml"
    if not p.exists():
        return {}
    try:
        return tomllib.loads(p.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        die(f"{p} is not valid TOML: {e}")
