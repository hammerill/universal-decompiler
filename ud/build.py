"""Configure and build the CMake project; keep the full log, print a short error summary.

    ud build                          # Release (or [build] config in ud.toml)
    ud build --config Debug
    ud build --target game -j 8
    ud build -D UD_WITH_SDL=OFF       # extra cache options (also: [build] options in ud.toml)
    ud build --fresh                  # wipe the CMake cache first
    ud build --json                   # {ok, errors: [{file, line, message}], warnings, log}

The full output goes to build/ud-build.log. The summary lists the first errors as file:line: message
(GCC, Clang, MSVC and linker formats). Exit code 1 on a failed configure or build.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from ud.common import OK, PROBLEM, emit_json, is_windows, load_config, repo_root, usage

ERROR_RX = [
    # gcc/clang: path:line:col: error: msg   |  path:line: error: msg
    re.compile(r"^(?P<file>[^\s:][^:]*?|[A-Za-z]:[^:]+?):(?P<line>\d+)(?::(?P<col>\d+))?:\s*(?:fatal )?error:\s*(?P<msg>.+)$"),
    # MSVC: path(line[,col]): error C1234: msg  (also "fatal error")
    re.compile(r"^\s*(?P<file>[^()\s][^()]*?)\((?P<line>\d+)(?:,(?P<col>\d+))?\):\s*(?:fatal )?error\s+(?P<code>[A-Z]+\d+)\s*:\s*(?P<msg>.+?)(?:\s*\[.*\])?$"),
    # MSVC linker / tools: file.obj : error LNK2019: msg
    re.compile(r"^\s*(?P<file>[^:\s][^:]*?)\s*:\s*(?:fatal )?error\s+(?P<code>LNK\d+|C\d+|MSB\d+)\s*:\s*(?P<msg>.+?)(?:\s*\[.*\])?$"),
    # GNU ld / lld
    re.compile(r"^(?P<file>[^:\s]+\.o(?:bj)?)?:?.*?(?P<msg>undefined reference to .+|undefined symbol: .+|multiple definition of .+)$"),
    # CMake configure errors
    re.compile(r"^CMake Error(?: at (?P<file>[^:]+):(?P<line>\d+))?.*?:?\s*(?P<msg>.*)$"),
]
WARN_RX = re.compile(r"(?:^|\s)warning(?:\s+C\d+)?\s*:", re.I)


def parse_errors(log: str, limit: int = 10) -> tuple[list[dict], int, int]:
    errors, seen = [], set()
    total = 0
    lines = log.splitlines()
    for i, ln in enumerate(lines):
        for rx in ERROR_RX:
            m = rx.match(ln.rstrip())
            if not m:
                continue
            d = {k: v for k, v in m.groupdict().items() if v}
            msg = d.get("msg", "").strip()
            if rx.pattern.startswith("^CMake Error") and not msg and i + 1 < len(lines):
                msg = lines[i + 1].strip()
            sig = (d.get("file"), d.get("line"), msg)
            if sig in seen:
                break
            seen.add(sig)
            total += 1
            if len(errors) < limit:
                errors.append(dict(file=d.get("file"), line=int(d["line"]) if d.get("line") else None,
                                   code=d.get("code"), message=msg[:300]))
            break
    warnings = sum(1 for ln in lines if WARN_RX.search(ln))
    return errors, total, warnings


def run_logged(cmd: list[str], cwd: Path, log) -> int:
    log.write(f"\n$ {' '.join(cmd)}\n")
    log.flush()
    p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    assert p.stdout
    for line in p.stdout:
        log.write(line)
    return p.wait()


def build(root: Path, config: str | None = None, target: str | None = None, jobs: int | None = None, defines: list[str] | None = None,
          generator: str | None = None, fresh: bool = False, max_errors: int = 10, source_dir: str | None = None,
          build_dir: str | None = None) -> dict:
    if not shutil.which("cmake"):
        usage("cmake is not on PATH (see `ud tools check`)")
    cfg = load_config(root).get("build", {})
    src = root / (source_dir or cfg.get("source_dir") or ".")
    out = root / (build_dir or cfg.get("build_dir") or "build")
    config = config or cfg.get("config") or "Release"
    generator = generator or cfg.get("generator") or os.environ.get("CMAKE_GENERATOR") or ""
    if not (src / "CMakeLists.txt").exists():
        usage(f"no CMakeLists.txt in {src} (ud init --scaffold writes a skeleton)")
    if fresh and (out / "CMakeCache.txt").exists():
        (out / "CMakeCache.txt").unlink()
        shutil.rmtree(out / "CMakeFiles", ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    logp = out / "ud-build.log"
    configure = ["cmake", "-S", str(src), "-B", str(out), f"-DCMAKE_BUILD_TYPE={config}"]
    if generator:
        configure += ["-G", generator]
    elif is_windows() and not (out / "CMakeCache.txt").exists() and not any("CMAKE_GENERATOR_PLATFORM" in d for d in (defines or [])):
        configure += ["-A", "x64"]          # 64-bit by default with the Visual Studio generator (32-bit: -D CMAKE_GENERATOR_PLATFORM=Win32)
    for d in list(cfg.get("options", [])) + [f"-D{x}" if not x.startswith("-D") else x for x in (defines or [])]:
        configure.append(d)
    t0 = time.time()
    with open(logp, "w", encoding="utf-8", newline="\n") as log:
        rc = run_logged(configure, root, log)
        stage = "configure"
        if rc == 0:
            stage = "build"
            b = ["cmake", "--build", str(out), "--config", config]
            if target:
                b += ["--target", target]
            b += ["--parallel"] + ([str(jobs)] if jobs else [])
            rc = run_logged(b, root, log)
    text = logp.read_text(encoding="utf-8", errors="replace")
    errors, nerr, nwarn = parse_errors(text, max_errors)
    exes = []
    for d in (out / "bin", out / config, out):
        if d.is_dir():
            exes += [p for p in d.iterdir() if p.is_file() and (p.suffix.lower() == ".exe" or (not p.suffix and os.access(p, os.X_OK)))]
    return dict(ok=rc == 0, stage=stage, exit_code=rc, config=config, seconds=round(time.time() - t0, 1), errors=errors,
                error_count=nerr, warning_count=nwarn, log=str(logp.relative_to(root) if logp.is_relative_to(root) else logp),
                executables=[str(p.relative_to(root)) if p.is_relative_to(root) else str(p) for p in exes[:10]])


def main(a):
    root = repo_root()
    r = build(root, a.config, a.target, a.jobs, a.define, a.generator, a.fresh, a.max_errors, a.source_dir, a.build_dir)
    if a.json:
        emit_json(r)
    else:
        if r["ok"]:
            print(f"build OK ({r['config']}, {r['seconds']} s, {r['warning_count']} warning lines). Log: {r['log']}")
            for e in r["executables"]:
                print(f"  -> {e}")
        else:
            print(f"{r['stage']} FAILED (exit {r['exit_code']}, {r['error_count']} errors, {r['seconds']} s). Full log: {r['log']}")
            for e in r["errors"]:
                loc = f"{e['file']}:{e['line']}" if e.get("line") else (e.get("file") or "")
                print(f"  {loc}: {e.get('code') + ': ' if e.get('code') else ''}{e['message']}")
            if r["error_count"] > len(r["errors"]):
                print(f"  ... {r['error_count'] - len(r['errors'])} more in the log")
            if not r["errors"]:
                print("  (no recognisable error lines: read the end of the log)")
    return OK if r["ok"] else PROBLEM


def register(sub):
    import argparse
    p = sub.add_parser("build", help="configure + build the CMake project; full log, short error summary",
                       description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", choices=["Debug", "Release", "RelWithDebInfo", "MinSizeRel"])
    p.add_argument("--target")
    p.add_argument("-j", "--jobs", type=int)
    p.add_argument("-D", "--define", action="append", help="extra CMake cache entry, e.g. -D UD_WITH_SDL=OFF")
    p.add_argument("-G", "--generator")
    p.add_argument("--fresh", action="store_true", help="delete CMakeCache.txt first")
    p.add_argument("--max-errors", type=int, default=10)
    p.add_argument("--source-dir")
    p.add_argument("--build-dir")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=main)
