"""Set up the current git repository as a decomp repo. Idempotent: run it again any time.

    git init my-decomp && cd my-decomp
    ud init                  # data/, .gitignore block, DECOMPLOG.md, DECOMP_PLAN.md, ud.toml, pre-push guard
    ud init --scaffold       # also a CMake + SDL3 platform-layer skeleton and tools/extract_assets.py
    ud init --json

What it does:
  data/                     created; the binary to decompile (and optionally its install) goes here
  .gitignore                a managed block: data/, build/, *.exe, *.dll, extracted-asset folders, Ghidra projects
  DECOMPLOG.md              the journal (only if missing)
  DECOMP_PLAN.md            done criterion, route, module map, middleware plan (only if missing)
  ud.toml                   settings read by ud build/run/assets/publish (only if missing)
  .git/hooks/pre-push       runs `ud publish check` before every push (an existing hook is kept and chained)

The repo is for local management only: the hook refuses pushes of the original, of extracted assets, and to
any public remote.
"""
from __future__ import annotations

import datetime as dt
import shutil
import stat
import sys
from pathlib import Path

from ud.common import OK, TEXT, emit_json, git, repo_root

TEMPLATES = Path(__file__).resolve().parent / "templates"
BEGIN, END = "# >>> universal-decompiler (ud init)", "# <<< universal-decompiler"
IGNORE = [
    "# never commit the original or anything extracted from it",
    "data/",
    "build/",
    "out/",
    "*.exe",
    "*.dll",
    "*.so",
    "*.dylib",
    "extracted/",
    "assets/extracted/",
    "# Ghidra / pyghidra-mcp projects embed the binary",
    "ghidra/",
    "pyghidra_mcp_projects/",
    "*.gpr",
    "*.rep/",
    "*.gzf",
    ".env",
]
HOOK_MARK = "universal-decompiler pre-push guard"


def gitignore(root: Path) -> str:
    p = root / ".gitignore"
    old = p.read_text(encoding="utf-8") if p.exists() else ""
    block = "\n".join([BEGIN, *IGNORE, END]) + "\n"
    if BEGIN in old and END in old:
        head, rest = old.split(BEGIN, 1)
        tail = rest.split(END, 1)[1].lstrip("\n")
        new = head + block + tail
    else:
        new = old + ("\n" if old and not old.endswith("\n") else "") + ("\n" if old.strip() else "") + block
    if new == old:
        return "unchanged"
    p.write_text(new, **TEXT)
    return "updated" if old else "created"


def launcher() -> str:
    """How the hook calls ud when it isn't on PATH: the repo's bin/ud, else this interpreter."""
    here = Path(__file__).resolve().parents[1]
    if (here / "bin" / "ud").exists():
        return f'"{(here / "bin" / "ud").as_posix()}"'
    return f'"{Path(sys.executable).as_posix()}" -m ud'


def hook_script() -> str:
    return f"""#!/bin/sh
# {HOOK_MARK} (installed by `ud init`; re-run it to refresh).
# Refuses pushes that would publish the original binary, extracted assets, or anything to a public remote.
# The decomp repo is for local management only.
remote="$1"
url="$2"
refs=$(cat)
here=$(dirname "$0")
if [ -x "$here/pre-push.local" ]; then
  printf '%s\\n' "$refs" | "$here/pre-push.local" "$@" || exit $?
fi
if command -v ud >/dev/null 2>&1; then
  ud publish check --remote "$remote" --url "$url"
else
  {launcher()} publish check --remote "$remote" --url "$url"
fi
status=$?
if [ $status -ne 0 ]; then
  echo "pre-push: blocked by ud publish check (exit $status)." >&2
  exit 1
fi
exit 0
"""


def install_hook(root: Path) -> str:
    r = git(["rev-parse", "--git-path", "hooks"], cwd=root, check=True)
    hooks = Path(r.stdout.strip())
    if not hooks.is_absolute():
        hooks = root / hooks
    hooks.mkdir(parents=True, exist_ok=True)
    hook = hooks / "pre-push"
    text = hook_script()
    status = "created"
    if hook.exists():
        old = hook.read_text(encoding="utf-8", errors="replace")
        if HOOK_MARK not in old:
            local = hooks / "pre-push.local"
            if local.exists():
                shutil.copyfile(hook, hooks / f"pre-push.local.{dt.datetime.now():%Y%m%d%H%M%S}")
            else:
                hook.rename(local)
            status = "installed (your existing pre-push hook now runs first as pre-push.local)"
        elif old == text:
            status = "unchanged"
        else:
            status = "updated"
    if status != "unchanged":
        hook.write_text(text, **TEXT)
        hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return status


def write_template(src: Path, dst: Path, subs: dict) -> str:
    if dst.exists():
        return "kept"
    dst.parent.mkdir(parents=True, exist_ok=True)
    text = src.read_text(encoding="utf-8")
    for k, v in subs.items():
        text = text.replace("{" + k + "}", v)
    dst.write_text(text, **TEXT)
    return "created"


def init(scaffold: bool = False) -> dict:
    root = repo_root()
    subs = dict(date=dt.date.today().isoformat(), name=root.name)
    res: dict = dict(repo=str(root), changes={})
    ch = res["changes"]
    data = root / "data"
    ch["data/"] = "kept" if data.is_dir() else "created"
    data.mkdir(exist_ok=True)
    ch[".gitignore"] = gitignore(root)
    for name in ("DECOMPLOG.md", "DECOMP_PLAN.md", "ud.toml"):
        ch[name] = write_template(TEMPLATES / name, root / name, subs)
    if scaffold:
        sc = TEMPLATES / "scaffold"
        for src in sorted(sc.rglob("*")):
            if src.is_file():
                rel = src.relative_to(sc).as_posix()
                ch[rel] = write_template(src, root / rel, subs)
    ch["pre-push hook"] = install_hook(root)
    binaries = [p.name for p in data.iterdir()] if data.is_dir() else []
    res["data_files"] = binaries[:20]
    res["next"] = ("put the binary to decompile into data/, then: ud scan data/<binary>" if not binaries
                   else f"ud scan data/{binaries[0]}" if len(binaries) == 1 else "ud scan data/")
    res["reminder"] = "This decomp repo is for local management only: keep it private (the pre-push hook enforces it)."
    return res


def main(a):
    r = init(a.scaffold)
    if a.json:
        emit_json(r)
        return OK
    print(f"decomp repo: {r['repo']}")
    for k, v in r["changes"].items():
        print(f"  {k:28} {v}")
    print(r["reminder"])
    print(f"next: {r['next']}")
    return OK


def register(sub):
    import argparse
    p = sub.add_parser("init", help="set up this git repo as a decomp repo (data/, .gitignore, journal, plan, pre-push guard)",
                       description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--scaffold", action="store_true", help="also write a CMake + SDL3 skeleton and tools/extract_assets.py")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=main)

