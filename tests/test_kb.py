"""ud kb: the repo's own notes, new/check/search round trip, rejection of decompiled code and address tables.
Parts derived from universal-modder's tests/test_um.py (MIT, Copyright (c) 2026 Rehan and universal-modder contributors)."""
from __future__ import annotations

import json
import shutil

from conftest import ROOT, ud

from ud import kb


def test_repo_knowledge_is_valid_and_index_current():
    root = ROOT / "knowledge"
    notes = kb.notes(root)
    assert len(notes) >= 3
    for p, _, _ in notes:
        fails, _ = kb.check_note(p, root)
        assert not fails, (p, fails)
    idx, _ = kb.build_index(root)
    assert (root / "INDEX.md").read_text(encoding="utf-8") == idx, "run `ud kb index`"


def scaffold(tmp_path):
    root = tmp_path / "knowledge"
    root.mkdir()
    shutil.copy(ROOT / "knowledge" / "TEMPLATE.md", root / "TEMPLATE.md")
    return root


def test_kb_new_check_search(tmp_path):
    root = scaffold(tmp_path)
    p = kb.new_note(root, "Foo Racer", "Clean-room reconstruction of Foo Racer", agent="Codex (gpt-6)", route="clean-room", family="native")
    assert p.parent.name == "foo-racer"
    fails, _ = kb.check_note(p, root)
    assert any("unfilled template text" in f for f in fails)       # a fresh scaffold must not pass
    good = p.read_text(encoding="utf-8")
    good = good.replace("FILL IN: exact build", "1.2 (GOG)")
    good = good.replace("> Two to four sentences: what you reconstructed", "> Rebuilt the race loop")
    good = good.replace("The most valuable section. Numbered; each one symptom -> cause -> fix.", "")
    good = good.replace("1. **Symptom.** What you saw. **Cause:** what it really was. **Fix:** what worked.",
                        "1. **Cars drift apart after a lap.** **Cause:** float order. **Fix:** keep the original's order.")
    p.write_text(good, encoding="utf-8")
    fails, _ = kb.check_note(p, root)
    assert not fails, fails
    res = kb.search(root, ["drift"])
    assert res and res[0]["path"].endswith("clean-room-reconstruction-of-foo-racer.md")
    assert kb.search(root, ["drift"], route="static-recomp") == []
    assert kb.search(root, [], family="native")


def test_kb_topic_note(tmp_path):
    root = scaffold(tmp_path)
    p = kb.new_note(root, None, "Typing vtables from RTTI", kind="topic", agent="a (m)")
    assert p.parent.name == "tooling"
    fails, _ = kb.check_note(p, root)
    assert any("unfilled template text" in f for f in fails) and any("tags" in f for f in fails)
    text = p.read_text(encoding="utf-8").replace("tags: []", "tags: [rtti, ghidra]")
    text = text.replace("> Two to four sentences: what this is for and when it saves time.", "> MSVC RTTI names classes.")
    text = text.replace("Numbered; each one symptom -> cause -> fix.\n", "")
    text = text.replace("1. **Symptom.** What you saw. **Cause:** what it really was. **Fix:** what worked.",
                        "1. **No class names.** **Cause:** RTTI analyzer off. **Fix:** enable it.")
    p.write_text(text, encoding="utf-8")
    fails, _ = kb.check_note(p, root)
    assert not fails, fails


def note(tmp_path, body):
    p = tmp_path / "n.md"
    p.write_text("---\nkind: topic\ntitle: t\nfamily: tooling\ntags: [x]\ndate: 2026-10-06\nagents: [a]\n---\n# t\n" + body, encoding="utf-8")
    return p


def test_kb_rejects_decompiled_code(tmp_path):
    dump = "```c\nundefined4 FUN_00401518(long param_1)\n{\n  uint uVar1;\n  uVar1 = *(uint *)(param_1 + 0x160);\n}\n```\n"
    fails, _ = kb.check_note(note(tmp_path, dump))
    assert any("decompiled output" in f for f in fails)


def test_kb_rejects_long_blocks_secrets_and_address_tables(tmp_path):
    code = "\n".join(f"int x{i} = {i};" for i in range(45))
    fails, _ = kb.check_note(note(tmp_path, f"```c\n{code}\n```\nkey sk-ant-{'a' * 30}\n"))
    assert any("code block" in f for f in fails) and any("Anthropic key" in f for f in fails)
    table = "\n".join(f"| 0x{0x401000 + 16 * i:08x} | func_{i} |" for i in range(45))
    fails, _ = kb.check_note(note(tmp_path, table))
    assert any("distinct addresses" in f for f in fails)
    fails, warns = kb.check_note(note(tmp_path, "A short own snippet:\n```cpp\nint add(int a, int b) { return a + b; }\n```\n"))
    assert not fails and not warns


def test_kb_impossible_date_is_reported(tmp_path):
    p = tmp_path / "n.md"
    p.write_text("---\nkind: topic\ntitle: t\ntags: [x]\ndate: 2026-02-31\nagents: [a]\n---\n# t\n", encoding="utf-8")
    fails, _ = kb.check_note(p)
    assert fails and "YAML" in fails[0]


def test_pr_head():
    assert kb.pr_head("kb/x", "git@github.com:someone/universal-decompiler.git") == "someone:kb/x"
    assert kb.pr_head("kb/x", None) == "kb/x"


def test_kb_cli(tmp_path):
    root = scaffold(tmp_path)
    assert ud("kb", "search", "anything", "--root", str(root)).returncode == 0
    r = ud("kb", "check", "--json", "--root", str(root))
    assert r.returncode == 0
    assert ud("kb", "check", "--index").returncode == 0     # the repo's own knowledge/
    assert ud("kb", "pr", str(ROOT / "knowledge" / "tooling" / "pyghidra-mcp-setup.md")).returncode == 0   # dry run only


def test_kb_index_show_and_new_json(tmp_path):
    root = scaffold(tmp_path)
    r = ud("kb", "new", "--kind", "topic", "--title", "A topic", "--agent", "a (m)", "--root", str(root), "--json")
    created = json.loads(r.stdout)["note"]
    assert r.returncode == 0 and created.endswith("a-topic.md")
    r = ud("kb", "index", "--root", str(root), "--json")
    assert json.loads(r.stdout)["notes"] == 1 and (root / "INDEX.md").exists() and (root / "index.json").exists()
    r = ud("kb", "show", "a-topic", "--root", str(root))
    assert r.returncode == 0 and "# A topic" in r.stdout
    assert ud("kb", "show", "nothing-here", "--root", str(root)).returncode == 2
    r = ud("kb", "pr", str(ROOT / "knowledge" / "tooling" / "pyghidra-mcp-setup.md"), "--json")
    assert json.loads(r.stdout)["dry_run"] is True


def test_kb_sync_mirrors_github(tmp_path, monkeypatch):
    """sync() with the GitHub tree API and raw files mocked: only knowledge/*.md|json are mirrored."""
    import io
    import urllib.request
    tree = {"tree": [{"path": "knowledge/INDEX.md", "type": "blob"}, {"path": "knowledge/tooling/a.md", "type": "blob"},
                     {"path": "ud/kb.py", "type": "blob"}, {"path": "knowledge/tooling", "type": "tree"}]}

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else req
        if "api.github.com" in url:
            return Resp(json.dumps(tree).encode())
        return Resp(f"content of {url.rsplit('/', 1)[-1]}".encode())

    monkeypatch.setenv("UD_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    root = kb.sync(quiet=True)
    files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    assert files == [".synced", "INDEX.md", "tooling/a.md"]
