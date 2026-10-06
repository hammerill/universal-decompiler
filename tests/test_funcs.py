"""ud funcs: import from every supported export format, set/range, stats, re-import keeps your work."""
from __future__ import annotations

import json

import pytest
from conftest import ud

from ud import funcs

GHIDRA = {"program": "game", "image_base": "0x00400000", "functions": [
    {"address": "0x401000", "name": "_DT_INIT", "namespace": "Global", "size": 27, "thunk": False, "external": False},
    {"address": "0x401170", "name": "strlen", "namespace": "<EXTERNAL>", "size": 10, "thunk": True, "external": False},
    {"address": "0x401518", "name": "FUN_00401518", "namespace": "Global", "size": 549, "thunk": False, "external": False},
    {"address": "0x402122", "name": "FUN_00402122", "namespace": "Global", "size": 1200, "thunk": False, "external": False},
    {"address": "0x1", "name": "puts", "namespace": "<EXTERNAL>", "size": 1, "thunk": False, "external": True},
]}
PYGHIDRA_MCP = {"symbols": [
    {"name": "FUN_00401518", "address": "00401518", "type": "Function", "namespace": "Global", "is_thunk": False},
    {"name": "FUN_00403000", "address": "00403000", "type": "Function", "namespace": "Global", "is_thunk": False},
    {"name": "memcpy", "address": "00401220", "type": "Function", "namespace": "<EXTERNAL>", "is_thunk": True},
]}


def write(repo, name, text):
    p = repo / name
    p.write_text(text if isinstance(text, str) else json.dumps(text), encoding="utf-8")
    return p


def test_import_ghidra_export_then_pyghidra_mcp(repo):
    r = funcs.do_import(repo, write(repo, "functions.json", GHIDRA))
    assert r == {"added": 4, "updated": 0, "skipped_thunks": 1, "total": 4}      # the external one is dropped
    data = funcs.load(repo)
    assert [f["address"] for f in data["functions"]] == ["0x00401000", "0x00401170", "0x00401518", "0x00402122"]
    assert next(f for f in data["functions"] if f["address"] == "0x00401170")["status"] == "skipped"
    funcs.do_set(repo, ["0x401518"], None, status="ported", name="move_enemies", module="world")
    r = funcs.do_import(repo, write(repo, "mcp.json", PYGHIDRA_MCP))
    assert r["added"] == 2 and r["updated"] == 1 and r["skipped_thunks"] == 1
    me = funcs.find(funcs.load(repo), "move_enemies")[0]
    assert me["status"] == "ported" and me["module"] == "world" and me["size"] == 549   # re-import kept our work


def test_import_csv_nm_ilspy_pairs(repo):
    csv = '"Name","Location","Type","Namespace"\n"main","00401136","Function","Global"\n"g_count","00404010","Data Label","Global"\n'
    assert funcs.do_import(repo, write(repo, "symbols.csv", csv))["added"] == 1
    nm = "0000000000401136 T main\n0000000000401200 t helper\n0000000000404010 D g_count\n"
    r = funcs.do_import(repo, write(repo, "nm.txt", nm))
    assert r["added"] == 1 and r["updated"] == 1
    ilspy = "Class Game.Player\nClass Game.World\nStruct Game.Vec2\n"
    r = funcs.do_import(repo, write(repo, "types.txt", ilspy), module="managed")
    assert r["added"] == 3
    w = funcs.find(funcs.load(repo), "Game.World")[0]
    assert w["address"] is None and w["module"] == "managed" and w["kind"] == "class"
    assert funcs.do_import(repo, write(repo, "pairs.txt", "0x500000 init_audio\n0x500100 mix\n"))["added"] == 2


def test_set_range_create_and_errors(repo):
    funcs.do_import(repo, write(repo, "functions.json", GHIDRA))
    ts = funcs.do_set(repo, [], "0x401000-0x401200", module="crt", status="skipped")
    assert len(ts) == 2
    funcs.do_set(repo, ["0x500000"], None, create=True, name="new_func")
    assert funcs.find(funcs.load(repo), "new_func")[0]["address"] == "0x00500000"
    with pytest.raises(SystemExit):
        funcs.do_set(repo, ["nope"], None, status="ported")


def test_stats(repo):
    funcs.do_import(repo, write(repo, "functions.json", GHIDRA))
    funcs.do_set(repo, ["0x401000"], None, status="skipped", module="crt")
    funcs.do_set(repo, ["0x401518"], None, status="verified", module="world")
    funcs.do_set(repo, ["0x402122"], None, status="reversed", module="world")
    s = funcs.stats(funcs.load(repo))
    w = s["modules"]["world"]
    assert w["total"] == 2 and w["verified"] == 1 and w["coverage"] == 50.0
    assert w["bytes_coverage"] == round(100 * 549 / (549 + 1200), 1)
    assert s["total"]["skipped"] == 2 and s["total"]["coverage"] == 50.0


def test_cli_round_trip(repo):
    write(repo, "functions.json", GHIDRA)
    assert ud("funcs", "import", "functions.json", cwd=repo).returncode == 0
    assert ud("funcs", "set", "0x402122", "--name", "main", "--status", "ported", "--module", "main", cwd=repo).returncode == 0
    lst = json.loads(ud("funcs", "list", "--status", "ported", "--json", cwd=repo).stdout)
    assert lst["count"] == 1 and lst["functions"][0]["name"] == "main"
    st = json.loads(ud("funcs", "stats", "--json", cwd=repo).stdout)
    assert st["modules"]["main"]["ported"] == 1
    assert ud("funcs", "set", "nothing-like-this", "--status", "ported", cwd=repo).returncode == 2
    text = ud("funcs", "stats", cwd=repo).stdout
    assert "TOTAL" in text
    assert (repo / "decomp" / "progress.json").exists()
