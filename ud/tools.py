"""Check the tools a route needs. Never installs anything: missing tools come with exact install steps for
Windows, Linux and macOS, which the agent hands to the user before stopping.

    ud tools check --route native        # Ghidra, JDK, pyghidra-mcp, CMake, a C++ compiler, ...
    ud tools check --route unity-il2cpp --json
    ud tools check                       # the route in ud.toml ([project] route = "..."), else the base toolchain
    ud tools list                        # every route and tool in the registry
    ud tools show ghidra                 # one tool: what it's for, where to get it

The registry is ud/tools.toml: adding a tool or a route needs no code change. `ud scan` prints the route to
check. Exit code 1 if a required tool is missing or too old.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tomllib
from functools import lru_cache
from pathlib import Path

from ud.common import OK, PROBLEM, emit_json, find_repo, load_config, os_key, usage

REGISTRY = Path(__file__).resolve().parent / "tools.toml"


@lru_cache(maxsize=1)
def registry() -> dict:
    return tomllib.loads(REGISTRY.read_text(encoding="utf-8"))


def route_tools(route: str) -> list[str]:
    """Required tool ids of a route (used by `ud scan`)."""
    return list(registry()["routes"][route]["required"])


def _expand(p: str) -> str:
    out = re.sub(r"%([^%]+)%", lambda m: os.environ.get(m.group(1), m.group(0)), p)
    return os.path.expanduser(os.path.expandvars(out))


def vkey(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:4])


def _version(cmd: list[str], rx: str | None) -> str | None:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20, encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = (r.stdout or "") + "\n" + (r.stderr or "")
    if rx:
        m = re.search(rx, out)
        return m.group(1) if m else None
    line = out.strip().splitlines()
    return line[0][:80] if line else None


def ghidra_extension_dirs() -> list[Path]:
    dirs = []
    g = os.environ.get("GHIDRA_INSTALL_DIR")
    if g:
        dirs += [Path(g) / "Ghidra" / "Extensions", Path(g) / "Extensions"]
    for base in (Path.home() / ".ghidra", Path(os.environ.get("APPDATA", "")) / "ghidra", Path.home() / ".config" / "ghidra"):
        if base.is_dir():
            dirs += [p / "Extensions" for p in base.glob("*") if p.is_dir()]
    return dirs


def check_tool(tid: str, spec: dict, osk: str | None = None) -> dict:
    osk = osk or os_key()
    res: dict = dict(id=tid, name=spec.get("name", tid), found=False, path=None, version=None, ok=False, homepage=spec.get("homepage"))
    platforms = spec.get("platforms", ["windows", "linux", "macos"])
    if osk not in platforms:
        res.update(available=False, note=f"not available on {osk} (runs on: {', '.join(platforms)})")
        return res
    res["available"] = True
    found_dir = None
    for b in spec.get("bin", []):
        p = shutil.which(b)
        if p:
            res.update(found=True, path=p)
            if spec.get("version"):
                res["version"] = _version([p, *spec["version"]], spec.get("version_regex"))
            break
    env = spec.get("env")
    if not res["found"] and env and os.environ.get(env):
        ep = Path(_expand(os.environ[env]))
        if ep.is_file():
            res.update(found=True, path=str(ep))
        elif ep.is_dir():
            files = spec.get("env_files", [])
            hit = next((ep / f for f in files if f != "." and (ep / f).exists()), None)
            if hit or not files:
                res.update(found=True, path=str(hit or ep))
                found_dir = ep
            else:
                res["note"] = f"${env} is set to {ep} but none of {', '.join(files)} is there"
        else:
            res["note"] = f"${env} points to {ep}, which doesn't exist"
    if not res["found"]:
        for p in spec.get("paths", []):
            q = Path(_expand(p))
            if q.exists():
                res.update(found=True, path=str(q))
                break
    if not res["found"] and spec.get("pkgconfig") and shutil.which("pkg-config"):
        v = _version(["pkg-config", "--modversion", spec["pkgconfig"]], r"([0-9][0-9.]*)")
        if v:
            res.update(found=True, path=f"pkg-config {spec['pkgconfig']}", version=v)
    if not res["found"] and spec.get("python_module"):
        py = shutil.which("python3") or shutil.which("python")
        if py:
            try:
                r = subprocess.run([py, "-c", f"import {spec['python_module']}"], capture_output=True, timeout=20)
                if r.returncode == 0:
                    res.update(found=True, path=f"python module {spec['python_module']} ({py})")
            except (OSError, subprocess.TimeoutExpired):
                pass
    if not res["found"] and spec.get("ghidra_extension"):
        for d in ghidra_extension_dirs():
            if (d / spec["ghidra_extension"]).is_dir():
                res.update(found=True, path=str(d / spec["ghidra_extension"]))
                break
    if res["found"] and spec.get("version_file") and found_dir:
        vf = found_dir / spec["version_file"]
        if vf.exists():
            m = re.search(spec.get("version_regex", r"([0-9.]+)"), vf.read_text(encoding="utf-8", errors="replace"))
            res["version"] = m.group(1) if m else None
    res["ok"] = res["found"]
    if res["found"] and spec.get("min_version"):
        if res["version"] and vkey(res["version"]) < vkey(spec["min_version"]):
            res["ok"] = False
            res["note"] = f"version {res['version']} is older than the required {spec['min_version']}"
        elif not res["version"]:
            res["note"] = f"couldn't read the version (needs {spec['min_version']}+)"
    install = spec.get("install", {})
    res["install"] = {k: install[k] for k in ("windows", "linux", "macos") if k in install}
    return res


def check_route(route: str, osk: str | None = None) -> dict:
    reg = registry()
    if route not in reg["routes"]:
        usage(f"unknown route {route!r}; routes: {', '.join(reg['routes'])}")
    r = reg["routes"][route]
    out: dict = dict(route=route, label=r.get("label", route), os=osk or os_key(), required=[], optional=[])
    for kind in ("required", "optional"):
        for tid in r.get(kind, []):
            spec: dict = reg["tools"].get(tid)  # type: ignore[assignment]
            if spec is None:
                usage(f"tools.toml: route {route} names unknown tool {tid!r}")
            out[kind].append(check_tool(tid, spec, osk))
    out["missing"] = [t["id"] for t in out["required"] if t.get("available", True) and not t["ok"]]
    out["unavailable_here"] = [t["id"] for t in out["required"] if not t.get("available", True)]
    out["ok"] = not out["missing"]
    return out


def format_check(r: dict) -> str:
    osk = r["os"] if r["os"] in ("windows", "linux", "macos") else "linux"
    L = [f"route {r['route']}: {r['label']}  (on {r['os']})"]
    for kind in ("required", "optional"):
        if not r[kind]:
            continue
        L.append(f"  {kind}:")
        for t in r[kind]:
            if not t.get("available", True):
                mark = "n/a "
            else:
                mark = " ok " if t["ok"] else ("OLD " if t["found"] else ("MISS" if kind == "required" else " -- "))
            ver = f" {t['version']}" if t.get("version") else ""
            where = f"  ({t['path']})" if t.get("path") else ""
            L.append(f"   [{mark}] {t['name']}{ver}{where}")
            if t.get("note"):
                L.append(f"          note: {t['note']}")
    missing = [t for t in r["required"] if t.get("available", True) and not t["ok"]]
    if missing:
        L.append("")
        L.append("MISSING: stop here and give the user these steps (the agent never installs tools itself):")
        for t in missing:
            L.append(f"\n  {t['name']}  — {t.get('homepage') or ''}")
            steps = t["install"].get(osk) or t["install"].get("linux") or t["install"].get("windows") or "see the homepage"
            for line in steps.splitlines():
                L.append(f"    {line}")
            other = "linux" if osk == "windows" else "windows"
            if t["install"].get(other):
                L.append(f"    ({other}: {t['install'][other].splitlines()[0]})")
        L.append("\nThen re-run: ud tools check --route " + r["route"])
    else:
        L.append("\nall required tools found")
    if r["unavailable_here"]:
        L.append(f"note: {', '.join(r['unavailable_here'])} don't run on {r['os']}; use a Windows machine for those steps")
    return "\n".join(L)


def main(a):
    if a.cmd == "list":
        reg = registry()
        if a.json:
            emit_json(dict(routes={k: v for k, v in reg["routes"].items()}, tools=sorted(reg["tools"])))
            return OK
        print("routes:")
        for k, v in reg["routes"].items():
            print(f"  {k:16} {v.get('label', '')}")
            print(f"  {'':16} required: {', '.join(v.get('required', []))}")
        print(f"\ntools ({len(reg['tools'])}): {', '.join(sorted(reg['tools']))}")
        return OK
    if a.cmd == "show":
        reg = registry()
        if a.tool not in reg["tools"]:
            usage(f"unknown tool {a.tool!r}; see `ud tools list`")
        r = check_tool(a.tool, reg["tools"][a.tool])
        if a.json:
            emit_json(r)
        else:
            spec = reg["tools"][a.tool]
            print(f"{r['name']}: {spec.get('description', '')}\n  homepage: {r.get('homepage')}\n  status:   "
                  f"{'found ' + str(r['path']) if r['found'] else 'not found'}" + (f" (version {r['version']})" if r.get("version") else ""))
            for k, v in r["install"].items():
                print(f"  install ({k}):\n    " + v.replace("\n", "\n    "))
        return OK if r["ok"] else PROBLEM
    # check
    route = a.route
    if not route:
        root = find_repo()
        route = (load_config(root).get("project", {}).get("route") if root else None) or "base"
    r = check_route(route)
    if a.json:
        emit_json(r)
    else:
        print(format_check(r))
    return OK if r["ok"] else PROBLEM


def register(sub):
    import argparse
    p = sub.add_parser("tools", help="check the tools a route needs; exact install steps (never installs)",
                       description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cs = p.add_subparsers(dest="cmd", metavar="<cmd>")
    q = cs.add_parser("check", help="check a route's tools", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    q.add_argument("--route", help="route id from `ud scan` / `ud tools list` (default: ud.toml's, else base)")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=main)
    q = cs.add_parser("list", help="routes and tools in the registry")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=main)
    q = cs.add_parser("show", help="one tool: description, status, install steps")
    q.add_argument("tool")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=main)
