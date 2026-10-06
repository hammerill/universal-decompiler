"""End-to-end check of the worked example, the way a user would run it. Used by CI and by tests/.

    uv run python examples/tinyquest/run_example.py            # work dir in a temp folder
    uv run python examples/tinyquest/run_example.py --work /tmp/tq --keep

1. builds the original (optimised, stripped) with CMake;
2. makes the dummy asset pack (the "user's own copy") and puts binary + pack into data/ of a fresh decomp repo
   (a copy of reconstruction/, `git init`-ed: a decomp repo is its own repository);
3. extracts the assets with tools/extract_assets.py, `ud assets check`;
4. `ud build`, then `ud run --compare` on several argument sets: stdout and exit code must match;
5. `ud publish check --offline` must pass (data/ and build/ are ignored) and `ud funcs stats` must work.
Exit code 0 when everything matches.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
EXE = ".exe" if os.name == "nt" else ""
CASES = [
    [],
    ["--seed", "1"],
    ["--seed", "42", "--render"],
    ["--inputs", "RRRRDDLLUU", "--ticks", "25"],
    ["--seed", "99", "--ticks", "200", "--render"],
    ["--inputs", "."],
    ["--seed", "4000000000", "--ticks", "120"],
]


def sh(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    print(f"$ {' '.join(cmd)}   (in {cwd})", flush=True)
    env = {**os.environ, "PYTHONPATH": str(REPO) + os.pathsep + os.environ.get("PYTHONPATH", ""), "UD_PUBLISH_OFFLINE": "1"}
    r = subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True, encoding="utf-8", errors="replace")
    out = (r.stdout + r.stderr).strip()
    if out:
        print("\n".join("  " + ln for ln in out.splitlines()[-25:]), flush=True)
    if check and r.returncode:
        raise SystemExit(f"FAILED ({r.returncode}): {' '.join(cmd)}")
    return r


def ud(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return sh([sys.executable, "-m", "ud", *args], cwd, check)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", help="work folder (default: a new temp folder)")
    ap.add_argument("--keep", action="store_true", help="keep the work folder")
    a = ap.parse_args()
    work = Path(a.work) if a.work else Path(tempfile.mkdtemp(prefix="ud-tinyquest-"))
    work.mkdir(parents=True, exist_ok=True)
    try:
        # 1. the original
        ob = work / "original-build"
        sh(["cmake", "-S", str(HERE / "original"), "-B", str(ob), "-DCMAKE_BUILD_TYPE=Release"]
           + (["-A", "x64"] if os.name == "nt" else []), work)
        sh(["cmake", "--build", str(ob), "--config", "Release"], work)
        orig = ob / "bin" / f"tinyquest{EXE}"
        # 2. a fresh decomp repo holding the user's copy in data/
        repo = work / "decomp"
        if repo.exists():
            shutil.rmtree(repo)
        shutil.copytree(HERE / "reconstruction", repo, ignore=shutil.ignore_patterns("build", "data"))
        (repo / "data").mkdir()
        shutil.copy2(orig, repo / "data" / orig.name)
        sh([sys.executable, str(HERE / "original" / "make_pack.py"), str(HERE / "original" / "assets_src"), str(repo / "data" / "tinyquest.pak")], work)
        sh(["git", "init", "-q"], repo)
        ud("scan", f"data/tinyquest{EXE}", cwd=repo)
        # 3. assets
        if ud("assets", "check", cwd=repo, check=False).returncode == 0:
            raise SystemExit("assets check passed before extraction: the check is broken")
        if shutil.which("uv"):
            sh(["uv", "run", "--script", "tools/extract_assets.py", "data"], repo)
        else:
            sh([sys.executable, "tools/extract_assets.py", "data"], repo)
        ud("assets", "check", cwd=repo)
        # 4. build + oracle comparison
        ud("build", "--config", "Release", cwd=repo)
        failures = 0
        for case in CASES:
            r = ud("run", "--compare", "--timeout", "30", "--", *case, cwd=repo, check=False)
            ok = r.returncode == 0 and "MATCH:" in r.stdout
            print(f"{'MATCH' if ok else 'DIFFERENT'}: {' '.join(case) or '(default demo)'}", flush=True)
            failures += not ok
        # 5. the repo must be safe to keep, and the tracker readable
        sh(["git", "add", "-A"], repo)
        sh(["git", "-c", "user.name=ud-example", "-c", "user.email=ud-example@localhost", "commit", "-qm", "reconstruction"], repo)
        ud("publish", "check", "--offline", cwd=repo)
        ud("funcs", "stats", cwd=repo)
        if failures:
            print(f"{failures} case(s) differ from the original")
            return 1
        print(f"example OK: {len(CASES)} cases identical to the original")
        return 0
    finally:
        if not a.keep and not a.work:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
