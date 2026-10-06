"""Check the extracted assets: runs tools/extract_assets.py --check and reports what's missing in data/.

    ud assets check            # exit 0: everything the rebuilt program loads is in data/; 1: something is missing
    ud assets check --json

The script contract (the asset-extraction skill writes the script): `--check` prints one `missing: <path>`
line per missing file and exits 1 if anything is missing. It's a single-file `uv run` script with inline
PEP 723 dependencies that reads only the user's own copy. Script path: ud.toml [assets] script
(default tools/extract_assets.py).
"""
from __future__ import annotations

import shutil
import subprocess
import sys

from ud.common import OK, PROBLEM, emit_json, load_config, repo_root, usage


def check(root=None) -> dict:
    root = root or repo_root()
    cfg = load_config(root)
    script = root / cfg.get("assets", {}).get("script", "tools/extract_assets.py")
    if not script.exists():
        usage(f"{script.relative_to(root)} doesn't exist yet: write it (asset-extraction skill; `ud init --scaffold` has a template)")
    data_dir = cfg.get("project", {}).get("data_dir") or "data"
    if shutil.which("uv"):
        cmd = ["uv", "run", "--quiet", "--script", str(script), "--check", "--out", data_dir]
    else:
        cmd = [sys.executable, str(script), "--check", "--out", data_dir]
    try:
        r = subprocess.run(cmd, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    except subprocess.TimeoutExpired:
        return dict(ok=False, script=str(script.relative_to(root)), error="the check timed out after 10 minutes", missing=[])
    out = (r.stdout or "") + (r.stderr or "")
    missing = [ln.split(":", 1)[1].strip() for ln in out.splitlines() if ln.lower().startswith("missing:")]
    return dict(ok=r.returncode == 0 and not missing, exit_code=r.returncode, script=str(script.relative_to(root).as_posix()),
                missing=missing, output=out.strip().splitlines()[-30:])


def main(a):
    r = check()
    if a.json:
        emit_json(r)
    else:
        if r.get("error"):
            print(f"ERROR: {r['error']}")
        elif r["ok"]:
            print(f"assets OK ({r['script']} --check)")
        else:
            print(f"assets INCOMPLETE ({len(r['missing'])} missing, exit {r['exit_code']}):")
            for m in r["missing"][:50]:
                print(f"  missing: {m}")
            if not r["missing"]:
                print("\n".join("  " + ln for ln in r["output"]))
            print("Fix: run the script against the user's own copy: uv run " + r["script"] + " \"<path to your copy>\"")
    return OK if r["ok"] else PROBLEM


def register(sub):
    import argparse
    p = sub.add_parser("assets", help="check that tools/extract_assets.py found everything in data/",
                       description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cs = p.add_subparsers(dest="cmd", metavar="<cmd>")
    q = cs.add_parser("check", help="run the extraction script's --check")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=main)
