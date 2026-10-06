"""The function progress tracker: decomp/progress.json (committed with the reconstruction).

    ud funcs import build/functions.json        # Ghidra export (ud/ghidra/ExportFunctions.java), pyghidra-mcp JSON,
                                                #   a CSV/TSV symbol table, `nm` output, or `ilspycmd -l c` type lists
    ud funcs import functions.json --module engine
    ud funcs list --status todo --module audio --limit 20
    ud funcs set 0x401a30 --name Game_Init --status ported --module core --note "WinMain -> here"
    ud funcs set --range 0x420000-0x42ffff --module audio
    ud funcs stats                              # coverage per module
    ud funcs stats --json

Each entry: address, original_name (what the decompiler or symbols called it), name (yours), module, status
(todo | reversed | ported | verified | skipped), note. Managed code has no addresses: entries are keyed by
name. Re-importing keeps your names, statuses and notes. Coverage = (ported + verified) / (all - skipped).

Getting the export:
  headless:   "$GHIDRA_INSTALL_DIR/support/analyzeHeadless" ghidra decomp -import data/game.exe \\
                -scriptPath "<ud>/ud/ghidra" -postScript ExportFunctions.java build/functions.json
  pyghidra-mcp: save the result of search_symbols_by_name(binary, ".*", functions_only=True, limit=...) (paginate)
              as JSON, then import it.
  managed:    ilspycmd -l c data/Game.dll > build/types.txt   (classes; methods come from the decompiled project)
"""
from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

from ud.common import OK, PROBLEM, TEXT, emit_json, repo_root, usage

STATUSES = ["todo", "reversed", "ported", "verified", "skipped"]
GHIDRA_DIR = Path(__file__).resolve().parent / "ghidra"


def store_path(root: Path) -> Path:
    return root / "decomp" / "progress.json"


def load(root: Path) -> dict:
    p = store_path(root)
    if not p.exists():
        return {"version": 1, "functions": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        usage(f"{p} is not valid JSON: {e}")
    data.setdefault("functions", [])
    return data


def save(root: Path, data: dict):
    p = store_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    data["functions"].sort(key=lambda f: (f.get("address") is None, int(f["address"], 16) if f.get("address") else 0, f.get("name") or f.get("original_name") or ""))
    p.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", **TEXT)


def norm_addr(a) -> str | None:
    if a is None or a == "":
        return None
    if isinstance(a, int):
        n = a
    else:
        s = str(a).strip().lower()
        s = s.split(":")[-1]              # "ram:00401000", "EXTERNAL:..." handled by the caller
        s = s[2:] if s.startswith("0x") else s
        if not re.fullmatch(r"[0-9a-f]+", s):
            return None
        n = int(s, 16)
    return f"0x{n:08x}" if n < 1 << 32 else f"0x{n:016x}"


def key(f: dict) -> str:
    return f.get("address") or f"name:{f.get('original_name') or f.get('name')}"


# --------------------------------------------------------------------------- parsers


def parse_json(text: str) -> list[dict]:
    data = json.loads(text)
    if isinstance(data, dict):
        for k in ("functions", "symbols", "results", "items", "data"):
            if isinstance(data.get(k), list):
                data = data[k]
                break
        else:
            data = [data]
    out = []
    for it in data:
        if isinstance(it, str):
            out.append(dict(original_name=it))
            continue
        if not isinstance(it, dict):
            continue
        if it.get("external") or str(it.get("address", "")).upper().startswith("EXTERNAL"):
            continue
        kind = str(it.get("type") or it.get("kind") or "function").lower()
        if kind not in ("function", "func", "thunk", "method", ""):
            continue
        addr = next((it[k] for k in ("address", "entry", "entry_point", "entrypoint", "addr", "start", "location") if k in it), None)
        name = next((it[k] for k in ("name", "function", "symbol", "label") if k in it), None)
        size = next((it[k] for k in ("size", "length", "body_size") if k in it), None)
        f: dict = dict(address=norm_addr(addr), original_name=name)
        if isinstance(size, int):
            f["size"] = size
        if it.get("thunk") or it.get("is_thunk"):       # Ghidra export / pyghidra-mcp
            f["thunk"] = True
        ns = it.get("namespace")
        if ns and ns not in ("Global", "<EXTERNAL>"):
            f["namespace"] = ns
        out.append(f)
    return out


def parse_text(text: str) -> list[dict]:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []
    first = lines[0]
    # CSV / TSV symbol tables with a header (Ghidra's Symbol Table export: "Name","Location","Type",...)
    if ("," in first or "\t" in first) and re.search(r"(?i)\b(address|location|entry)\b", first):
        dialect = "excel-tab" if "\t" in first else "excel"
        rows = list(csv.DictReader(io.StringIO(text), dialect=dialect))
        out = []
        for r in rows:
            low = {k.strip().lower(): (v or "").strip() for k, v in r.items() if k}
            if low.get("type") and low["type"].lower() not in ("function", "thunk function", "func"):
                continue
            addr = low.get("address") or low.get("location") or low.get("entry")
            if addr and addr.upper().startswith("EXTERNAL"):
                continue
            f: dict = dict(address=norm_addr(addr), original_name=low.get("name") or low.get("symbol"))
            if (low.get("size") or "").isdigit():
                f["size"] = int(low["size"])
            out.append(f)
        return out
    # nm: "0000000000401136 T main"
    nm = [re.match(r"^\s*([0-9a-fA-F]{4,16})\s+([TtWw])\s+(\S+)", ln) for ln in lines]
    if sum(1 for m in nm if m) >= max(1, len(lines) // 2):
        return [dict(address=norm_addr(m.group(1)), original_name=m.group(3)) for m in nm if m]
    # ilspycmd -l c|s|i|e|d : "Class Namespace.Type"
    il = [re.match(r"^(Class|Struct|Interface|Enum|Delegate)\s+(\S+)", ln) for ln in lines]
    if sum(1 for m in il if m) >= max(1, len(lines) // 2):
        return [dict(address=None, original_name=m.group(2), kind=m.group(1).lower()) for m in il if m]
    # "0x401000 name" pairs, else one name per line
    pairs = [re.match(r"^\s*(?:0x)?([0-9a-fA-F]{4,16})[\s,;]+(\S+)", ln) for ln in lines]
    if sum(1 for m in pairs if m) >= max(1, len(lines) // 2):
        return [dict(address=norm_addr(m.group(1)), original_name=m.group(2)) for m in pairs if m]
    return [dict(address=None, original_name=ln.strip()) for ln in lines]


def parse_any(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace").lstrip("﻿")
    if text.lstrip()[:1] in ("[", "{"):
        try:
            return parse_json(text)
        except json.JSONDecodeError:
            pass
    return parse_text(text)


# --------------------------------------------------------------------------- operations


def do_import(root: Path, src: Path, module: str | None = None, skip_thunks: bool = True) -> dict:
    data = load(root)
    by_key = {key(f): f for f in data["functions"]}
    added = updated = skipped = 0
    for it in parse_any(src):
        if not it.get("address") and not it.get("original_name"):
            continue
        k = it["address"] or f"name:{it['original_name']}"
        cur = by_key.get(k)
        if cur is None:
            cur = dict(address=it.get("address"), original_name=it.get("original_name"), name=None, module=module,
                       status="todo", note="")
            if it.get("thunk") and skip_thunks:
                cur.update(status="skipped", note="thunk")
                skipped += 1
            data["functions"].append(cur)
            by_key[k] = cur
            added += 1
        else:
            if it.get("original_name") and cur.get("original_name") != it["original_name"] and not cur.get("name"):
                cur["original_name"] = it["original_name"]
            if module and not cur.get("module"):
                cur["module"] = module
            updated += 1
        for extra in ("size", "namespace", "kind"):
            if it.get(extra) is not None:
                cur[extra] = it[extra]
    data.setdefault("sources", [])
    rel = src.resolve().relative_to(root).as_posix() if src.resolve().is_relative_to(root) else str(src)
    if rel not in data["sources"]:
        data["sources"].append(rel)
    save(root, data)
    return dict(added=added, updated=updated, skipped_thunks=skipped, total=len(data["functions"]))


def find(data: dict, ident: str) -> list[dict]:
    a = norm_addr(ident) if re.fullmatch(r"(?:0x)?[0-9a-fA-F]{4,16}", ident) else None
    res = [f for f in data["functions"] if (a and f.get("address") == a) or f.get("name") == ident or f.get("original_name") == ident]
    return res


def do_set(root: Path, idents: list[str], rng: str | None, status=None, name=None, module=None, note=None, create=False) -> list[dict]:
    data = load(root)
    targets: list[dict] = []
    if rng:
        m = re.fullmatch(r"\s*(?:0x)?([0-9a-fA-F]+)\s*[-:]\s*(?:0x)?([0-9a-fA-F]+)\s*", rng)
        if not m:
            usage("--range wants START-END in hex, e.g. 0x420000-0x42ffff")
        lo, hi = int(m.group(1), 16), int(m.group(2), 16)
        targets += [f for f in data["functions"] if f.get("address") and lo <= int(f["address"], 16) <= hi]
    for ident in idents:
        hit = find(data, ident)
        if not hit:
            if not create:
                usage(f"no function {ident!r} in decomp/progress.json (add it with --create, or import first)")
            a = norm_addr(ident) if re.fullmatch(r"(?:0x)?[0-9a-fA-F]{4,16}", ident) else None
            f = dict(address=a, original_name=None if a else ident, name=None, module=None, status="todo", note="")
            data["functions"].append(f)
            hit = [f]
        if len(hit) > 1 and name:
            usage(f"{ident!r} matches {len(hit)} functions; use the address")
        targets += hit
    if not targets:
        usage("nothing selected: give addresses/names or --range")
    for f in targets:
        if status:
            f["status"] = status
        if name is not None:
            f["name"] = name or None
        if module is not None:
            f["module"] = module or None
        if note is not None:
            f["note"] = note
    save(root, data)
    return targets


def stats(data: dict) -> dict:
    mods: dict[str, dict] = {}
    for f in data["functions"]:
        m = f.get("module") or "(unassigned)"
        s = mods.setdefault(m, {**{k: 0 for k in STATUSES}, "total": 0, "bytes": 0, "bytes_done": 0})
        st = f.get("status", "todo")
        s[st] = s.get(st, 0) + 1
        s["total"] += 1
        if isinstance(f.get("size"), int) and st != "skipped":
            s["bytes"] += f["size"]
            if st in ("ported", "verified"):
                s["bytes_done"] += f["size"]

    def cov(s):
        base = s["total"] - s["skipped"]
        s["coverage"] = round(100 * (s["ported"] + s["verified"]) / base, 1) if base else 0.0
        s["verified_pct"] = round(100 * s["verified"] / base, 1) if base else 0.0
        s["bytes_coverage"] = round(100 * s["bytes_done"] / s["bytes"], 1) if s["bytes"] else None
        return s

    total = {**{k: 0 for k in STATUSES}, "total": 0, "bytes": 0, "bytes_done": 0}
    for s in mods.values():
        for k in total:
            total[k] += s[k]
    return dict(modules={k: cov(v) for k, v in sorted(mods.items())}, total=cov(total))


def fmt_row(f: dict) -> str:
    nm = f.get("name") or "-"
    orig = f.get("original_name") or ""
    return f"{f.get('address') or '':<12} {f.get('status', 'todo'):<9} {(f.get('module') or '-'):<14} {nm:<32} {orig:<32} {f.get('note') or ''}"


def main(a):
    root = repo_root()
    c = a.cmd
    if c == "import":
        src = Path(a.source)
        if not src.exists():
            usage(f"no such file: {src}")
        r = do_import(root, src, a.module, skip_thunks=not a.keep_thunks)
        if a.json:
            emit_json(r)
        else:
            print(f"imported {src}: {r['added']} new, {r['updated']} already tracked, {r['skipped_thunks']} thunks marked skipped; "
                  f"{r['total']} functions in decomp/progress.json")
        return OK if r["added"] or r["updated"] else PROBLEM
    data = load(root)
    if c == "list":
        fs = data["functions"]
        if a.status:
            fs = [f for f in fs if f.get("status") == a.status]
        if a.module:
            fs = [f for f in fs if (f.get("module") or "") == a.module]
        if a.grep:
            rx = re.compile(a.grep, re.I)
            fs = [f for f in fs if rx.search(" ".join(str(f.get(k) or "") for k in ("name", "original_name", "note", "address")))]
        n = len(fs)
        fs = fs[: a.limit] if a.limit else fs
        if a.json:
            emit_json(dict(count=n, functions=fs))
            return OK
        print(f"{'address':<12} {'status':<9} {'module':<14} {'name':<32} {'original':<32} note")
        for f in fs:
            print(fmt_row(f))
        if n > len(fs):
            print(f"... {n - len(fs)} more (--limit 0 for all)")
        return OK
    if c == "set":
        ts = do_set(root, a.ids, a.range, a.status, a.name, a.module, a.note, a.create)
        if a.json:
            emit_json(dict(updated=ts))
        else:
            for f in ts[:20]:
                print(fmt_row(f))
            if len(ts) > 20:
                print(f"... and {len(ts) - 20} more")
            print(f"updated {len(ts)} function(s)")
        return OK
    if c == "stats":
        s = stats(data)
        if a.json:
            emit_json(s)
            return OK
        if not data["functions"]:
            print("decomp/progress.json is empty: run `ud funcs import <export>` first")
            return PROBLEM
        print(f"{'module':<18} {'total':>6} {'todo':>6} {'rev':>6} {'port':>6} {'verif':>6} {'skip':>6} {'cover':>7} {'bytes':>7}")
        rows = list(s["modules"].items()) + [("TOTAL", s["total"])]
        for m, v in rows:
            b = f"{v['bytes_coverage']}%" if v.get("bytes_coverage") is not None else "-"
            print(f"{m:<18} {v['total']:>6} {v['todo']:>6} {v['reversed']:>6} {v['ported']:>6} {v['verified']:>6} {v['skipped']:>6} "
                  f"{v['coverage']:>6}% {b:>7}")
        return OK
    usage("give a command: import, list, set or stats")


def register(sub):
    import argparse
    p = sub.add_parser("funcs", help="function progress tracker (decomp/progress.json): import, list, set, stats",
                       description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cs = p.add_subparsers(dest="cmd", metavar="<cmd>")
    q = cs.add_parser("import", help="import functions from a Ghidra/pyghidra-mcp export, symbol table, nm or ilspycmd listing")
    q.add_argument("source")
    q.add_argument("--module", help="module to assign to newly imported entries")
    q.add_argument("--keep-thunks", action="store_true", help="don't mark thunks as skipped")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=main)
    q = cs.add_parser("list", help="list tracked functions")
    q.add_argument("--status", choices=STATUSES)
    q.add_argument("--module")
    q.add_argument("--grep", help="regex over name, original name, note, address")
    q.add_argument("--limit", type=int, default=50, help="0 = all (default 50)")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=main)
    q = cs.add_parser("set", help="update functions by address/name or address range")
    q.add_argument("ids", nargs="*", help="addresses (0x401a30) or names")
    q.add_argument("--range", help="hex address range START-END")
    q.add_argument("--status", choices=STATUSES)
    q.add_argument("--name", help="your name for it ('' clears)")
    q.add_argument("--module", help="module ('' clears)")
    q.add_argument("--note")
    q.add_argument("--create", action="store_true", help="add the function if it isn't tracked yet")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=main)
    q = cs.add_parser("stats", help="coverage per module")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=main)
