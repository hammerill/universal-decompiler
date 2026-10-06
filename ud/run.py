"""Launch the rebuilt program (or the original), capture its output and logs, take screenshots, and kill it
by its exact PID at the timeout. The original's behaviour is the oracle; compare against it.

    ud run                                  # the rebuilt program from ud.toml [run] exe (else build/bin/*)
    ud run --timeout 20 --shot              # screenshot after 5 s (or --shot-at 12), kill at 20 s
    ud run --original --timeout 20 --shot   # the same for the original (ud.toml [run] original)
    ud run --compare --timeout 30 -- --frames 300 --headless   # both, same args: does stdout match?
    ud run --json -- <args for the program>

Output lands in build/ud-run/<rebuilt|original>-<time>/: stdout.txt, stderr.txt, shot-*.png, copies of the
log files listed in ud.toml [run] logs. Being killed at the timeout is expected for GUI programs. A crash
(death by a signal, or a Windows exception code such as 0xC0000005) gives exit code 1, and so does a
--compare mismatch; an ordinary non-zero exit code is reported, not treated as a failure.

Screenshots: Windows (also from WSL) with PrintWindow on the process's own window; Linux X11 via
xdotool + ImageMagick `import`; Wayland via grim (whole screen, best effort); macOS via screencapture.
Never kill by name pattern: this only ever kills the PID (and process group/tree) it started.
"""
from __future__ import annotations

import base64
import datetime as dt
import glob
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

from ud.common import OK, PROBLEM, emit_json, is_mac, is_windows, is_wsl, load_config, ps_exe, repo_root, to_win, usage

PS1 = Path(__file__).resolve().parent / "ps1" / "WinShot.ps1"


def resolve_exe(root: Path, cfg: dict, original: bool, override: str | None) -> Path:
    run = cfg.get("run", {})
    val = override or (run.get("original") if original else run.get("exe"))
    if not val:
        if original:
            usage("no original configured: set [run] original = \"data/<file>\" in ud.toml or pass --exe")
        cands = []
        for d in (root / "build" / "bin", root / "build" / "Release", root / "build" / "Debug", root / "build"):
            if d.is_dir():
                cands += [p for p in d.iterdir() if p.is_file() and (p.suffix.lower() == ".exe" or (not p.suffix and os.access(p, os.X_OK)))]
        if len(cands) == 1:
            return cands[0]
        usage("set [run] exe in ud.toml (the rebuilt program)" + (f"; candidates: {', '.join(str(c) for c in cands[:5])}" if cands else
                                                                 "; nothing built yet (ud build)"))
    p = (root / val) if not Path(val).is_absolute() else Path(val)
    if not p.exists() and is_windows() and p.suffix == "":
        p = p.with_suffix(".exe")
    if not p.exists():
        usage(f"not found: {p} (build first: ud build)" if not original else f"not found: {p}")
    return p


# --------------------------------------------------------------------------- screenshots

def shot_windows(out: Path, pid: int | None, name: str | None) -> str:
    target = to_win(out) if is_wsl() else str(out)
    pre = f"$TargetPid = {int(pid or 0)}; $Name = '{(name or '').replace(chr(39), '')}'; $Out = '{target.replace(chr(39), chr(39) * 2)}';\n"
    script = pre + PS1.read_text(encoding="utf-8")
    enc = base64.b64encode(script.encode("utf-16-le")).decode()
    try:
        r = subprocess.run([ps_exe(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", enc],
                           capture_output=True, text=True, timeout=60, cwd="/mnt/c" if is_wsl() else None)
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"error: {e}"
    msg = (r.stdout or r.stderr).strip().splitlines()
    return msg[-1] if msg else f"error: powershell exit {r.returncode}"


def shot_posix(out: Path, pid: int) -> str:
    if is_mac():
        r = subprocess.run(["screencapture", "-x", str(out)], capture_output=True)
        return "ok (whole screen, screencapture)" if r.returncode == 0 else "error: screencapture failed"
    if os.environ.get("DISPLAY") and shutil.which("xdotool") and shutil.which("import"):
        wins = subprocess.run(["xdotool", "search", "--onlyvisible", "--pid", str(pid)], capture_output=True, text=True).stdout.split()
        if wins:
            r = subprocess.run(["import", "-window", wins[-1], str(out)], capture_output=True, text=True)
            if r.returncode == 0:
                return f"ok (X11 window {wins[-1]})"
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("grim"):
        r = subprocess.run(["grim", str(out)], capture_output=True)
        if r.returncode == 0:
            return "ok (whole screen, grim)"
    if os.environ.get("DISPLAY") and shutil.which("import"):
        r = subprocess.run(["import", "-window", "root", str(out)], capture_output=True)
        if r.returncode == 0:
            return "ok (whole X11 screen)"
    return "error: no screenshot tool (install xdotool + imagemagick, or grim on Wayland)"


def take_shot(out: Path, pid: int, exe: Path) -> str:
    if is_windows() or (is_wsl() and exe.suffix.lower() == ".exe"):
        return shot_windows(out, pid if is_windows() else None, exe.stem if is_wsl() else None)
    return shot_posix(out, pid)


# --------------------------------------------------------------------------- process control

def kill_tree(p: subprocess.Popen, exe: Path, started: float):
    """Exact-PID kill: the process (Windows: its tree via taskkill /T; POSIX: the session/group we created)."""
    if p.poll() is not None:
        return
    if is_windows():
        subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
    else:
        try:
            os.killpg(p.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            p.terminate()
        try:
            p.wait(3)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                p.kill()
        if is_wsl() and exe.suffix.lower() == ".exe":
            # the Windows side of a WSL-launched .exe has its own PID: find exactly the one we started (by name + start time)
            ps = (f"Get-Process -Name '{exe.stem}' -ErrorAction SilentlyContinue | Where-Object {{ $_.StartTime -ge "
                  f"[DateTime]::Parse('{dt.datetime.fromtimestamp(started - 2).isoformat()}') }} | ForEach-Object {{ $_.Id }}")
            r = subprocess.run([ps_exe(), "-NoProfile", "-Command", ps], capture_output=True, text=True, cwd="/mnt/c")
            for wpid in r.stdout.split():
                if wpid.isdigit():
                    subprocess.run(["taskkill.exe", "/PID", wpid, "/T", "/F"], capture_output=True, cwd="/mnt/c")
    try:
        p.wait(5)
    except subprocess.TimeoutExpired:
        pass


def tail(path: Path, n: int = 40) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    except OSError:
        return []


def launch(root: Path, cfg: dict, original: bool, exe_override: str | None, args: list[str] | None, timeout: float, shot: bool,
           shot_at: float | None, label: str | None = None) -> dict:
    run = cfg.get("run", {})
    exe = resolve_exe(root, cfg, original, exe_override)
    if args is None or not args:
        args = list(run.get("original_args" if original else "args", []) or [])
    if original:
        oc = run.get("original_cwd")
        cwd = (root / oc) if oc else exe.parent
    else:
        cwd = root / (run.get("cwd") or ".")
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = root / "build" / "ud-run" / f"{label or ('original' if original else 'rebuilt')}-{stamp}"
    outdir.mkdir(parents=True, exist_ok=True)
    so, se = open(outdir / "stdout.txt", "wb"), open(outdir / "stderr.txt", "wb")
    kw: dict = {}
    if is_windows():
        kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    else:
        kw["start_new_session"] = True
    t0 = time.time()
    try:
        p = subprocess.Popen([str(exe), *args], cwd=cwd, stdout=so, stderr=se, stdin=subprocess.DEVNULL, **kw)
    except OSError as e:
        so.close()
        se.close()
        return dict(ok=False, exe=str(exe), error=f"could not start: {e}", run_dir=str(outdir))
    shots, timed_out = [], False
    when = shot_at if shot_at is not None else min(5.0, timeout / 2)
    shot_done = not shot
    while True:
        rc = p.poll()
        if rc is not None:
            break
        el = time.time() - t0
        if not shot_done and el >= when:
            f = outdir / f"shot-{int(el)}s.png"
            res = take_shot(f, p.pid, exe)
            shots.append(dict(file=str(f.relative_to(root)), result=res))
            shot_done = True
        if el >= timeout:
            timed_out = True
            kill_tree(p, exe, t0)
            break
        time.sleep(0.1)
    so.close()
    se.close()
    dur = round(time.time() - t0, 2)
    rc = p.returncode
    logs = []
    for pattern in run.get("logs", []) or []:
        for m in glob.glob(str(cwd / pattern), recursive=True):
            mp = Path(m)
            if mp.is_file() and mp.stat().st_mtime >= t0 - 1:
                dst = outdir / mp.name
                shutil.copy2(mp, dst)
                logs.append(str(dst.relative_to(root)))
    # a crash is death by signal (POSIX: negative return code) or an NTSTATUS exception code (0xC0000005 access
    # violation, ...); a plain non-zero exit is the program's own answer and is reported, not judged
    crashed = not timed_out and rc is not None and (rc < 0 or (rc & 0xFFFFFFFF) >= 0xC0000000)
    return dict(ok=not crashed, crashed=crashed, exe=str(exe), args=args, cwd=str(cwd), pid=p.pid, exit_code=None if timed_out else rc, timed_out=timed_out,
                seconds=dur, run_dir=str(outdir.relative_to(root)), stdout_tail=tail(outdir / "stdout.txt"),
                stderr_tail=tail(outdir / "stderr.txt"), screenshots=shots, logs=logs)


def compare(a: dict, b: dict, root: Path) -> dict:
    sa = (root / a["run_dir"] / "stdout.txt").read_text(encoding="utf-8", errors="replace").splitlines()
    sb = (root / b["run_dir"] / "stdout.txt").read_text(encoding="utf-8", errors="replace").splitlines()
    first = next((i for i, (x, y) in enumerate(zip(sa, sb, strict=False)) if x != y), None)
    if first is None and len(sa) != len(sb):
        first = min(len(sa), len(sb))
    same = first is None and a.get("exit_code") == b.get("exit_code")
    out = dict(stdout_identical=first is None, exit_codes=[a.get("exit_code"), b.get("exit_code")], match=same,
               lines=[len(sa), len(sb)])
    if first is not None:
        out["first_difference"] = dict(line=first + 1, original=sa[first] if first < len(sa) else "<end>",
                                       rebuilt=sb[first] if first < len(sb) else "<end>")
    return out


def print_run(r: dict):
    if r.get("error"):
        print(f"{r['exe']}: {r['error']}")
        return
    state = f"killed at the {r['seconds']} s timeout" if r["timed_out"] else f"exited {r['exit_code']} after {r['seconds']} s"
    print(f"{r['exe']} (pid {r['pid']}): {state}{'  CRASHED' if r.get('crashed') else ''}")
    print(f"  output: {r['run_dir']}/")
    for s in r["screenshots"]:
        print(f"  screenshot: {s['file']}  [{s['result']}]")
    for lg in r["logs"]:
        print(f"  log: {lg}")
    if r["stdout_tail"]:
        print("  stdout (tail):")
        for ln in r["stdout_tail"][-15:]:
            print(f"    {ln}")
    if r["stderr_tail"]:
        print("  stderr (tail):")
        for ln in r["stderr_tail"][-15:]:
            print(f"    {ln}")


def main(a):
    root = repo_root()
    cfg = load_config(root)
    args = a.args[1:] if a.args and a.args[0] == "--" else a.args
    if a.compare:
        o = launch(root, cfg, True, None, args, a.timeout, a.shot, a.shot_at, "original")
        r = launch(root, cfg, False, a.exe, args, a.timeout, a.shot, a.shot_at, "rebuilt")
        if o.get("error") or r.get("error"):
            res: dict = dict(original=o, rebuilt=r, comparison=None, ok=False)
        else:
            res = dict(original=o, rebuilt=r, comparison=compare(o, r, root))
            res["ok"] = res["comparison"]["match"]
        if a.json:
            emit_json(res)
        else:
            print_run(o)
            print_run(r)
            c = res["comparison"]
            if c:
                if c["match"]:
                    print(f"MATCH: stdout identical ({c['lines'][0]} lines), same exit code")
                else:
                    d = c.get("first_difference")
                    print(f"DIFFERENT: exit codes {c['exit_codes']}" + (f"; first difference at line {d['line']}:\n  original: {d['original']}\n"
                                                                       f"  rebuilt:  {d['rebuilt']}" if d else ""))
        return OK if res["ok"] else PROBLEM
    r = launch(root, cfg, a.original, a.exe, args, a.timeout, a.shot, a.shot_at)
    if a.json:
        emit_json(r)
    else:
        print_run(r)
    return OK if r.get("ok") else PROBLEM


def register(sub):
    import argparse
    p = sub.add_parser("run", help="launch the rebuilt program or the original; capture, screenshot, kill by PID",
                       description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--original", action="store_true", help="run the original instead of the rebuilt program")
    p.add_argument("--compare", action="store_true", help="run both with the same args and compare stdout + exit code")
    p.add_argument("--exe", help="program to run instead of ud.toml's")
    p.add_argument("--timeout", type=float, default=30.0, help="seconds before the process is killed (default 30)")
    p.add_argument("--shot", action="store_true", help="take a window screenshot")
    p.add_argument("--shot-at", type=float, help="seconds after launch for the screenshot (default min(5, timeout/2))")
    p.add_argument("--json", action="store_true")
    p.add_argument("args", nargs=argparse.REMAINDER, help="arguments for the program (after --)")
    p.set_defaults(func=main)
