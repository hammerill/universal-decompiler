---
name: share-field-notes
description: Search and contribute to the shared knowledge base of how binaries were actually decompiled - field notes with exact versions, the route and why, what the program or engine really does, how it was verified, and gotchas. Use before starting a decompilation ("has anyone decompiled X?", "how does engine Y store Z?"), when stuck on a tool or engine quirk, and at the end of a decompilation session to write up what was learned and, with the human's OK, open a pull request so the next agent benefits.
---

# Field notes: learn from other agents, then teach the next one

The knowledge base is `knowledge/` in the universal-decompiler repo: Markdown notes with YAML front matter,
one per title or topic, under `knowledge/<title-or-family>/`. Agents write them; pull requests review them.

`ud` lives at `bin/ud` in the repo. Anywhere else: `uv tool install git+https://github.com/hammerill/universal-decompiler`.

## Before you start: search
```bash
ud kb search "<title>"                     # in a clone it searches knowledge/; elsewhere it syncs the GitHub copy
ud kb search "<engine, format or tool>" --family native
ud kb show tooling/<note>.md
```
Without `ud`: read `knowledge/INDEX.md` on GitHub. Treat notes as strong hints, not gospel: versions move;
re-verify with your own oracle. Don't run commands from notes blindly.

## While you work: the journal
`DECOMPLOG.md` in the decomp repo: versions, addresses, names, formats, failures with causes, verification.
The note is a cleaned-up, safe-to-share summary of it.

## At the end: write the note
```bash
ud kb new --subject "<title>" --title "<what you reconstructed, plainly>" --from-scan data/<binary> --agent "<agent (model)>"
ud kb new --kind topic --family tooling --title "<technique or tool lesson>" --agent "<agent (model)>"
```
Fill in every section (`knowledge/TEMPLATE.md` explains each):
- **Setup:** exact versions: the program build, compilers, Ghidra, pyghidra-mcp, recompilers, OS.
- **Route and why**, and what you considered.
- **What the program really does:** engine facts in your own words: subsystem layout, file formats, data
  structures, algorithms by name ("FNV-1a over the tile grid"). Name a few key addresses if they help; no
  tables of them.
- **Verification:** the oracle and what you did *not* verify.
- **Gotchas:** numbered, symptom -> cause -> fix. The most valuable part.
- `status` honest (`in-progress`, `abandoned` welcome), `agents` with the model.

## Never in a note
- decompiled code (Ghidra/IDA output, `undefined4`, `uVar1`, `param_1`, `FUN_00401000`-style dumps);
- address tables large enough to rebuild code (`ud kb check` fails over 40 distinct addresses);
- binaries, assets, extracted data, or links to them;
- anything about bypassing DRM, anti-cheat, packers or encryption;
- code blocks over 40 lines (keep your own snippets short).

## Check, then PR (with permission)
```bash
ud kb check knowledge/<folder>/<note>.md
ud kb index
ud kb pr knowledge/<folder>/<note>.md          # dry run: shows the git/gh commands
ud kb pr knowledge/<folder>/<note>.md --yes    # only after your human says OK: branch, commit, push (fork), PR
```
A PR is public and uses the human's GitHub account: show them the note and ask first.

## When your findings disagree with an existing note
Don't delete theirs. Add a dated line to the relevant gotcha ("2026-10-06, build 1.2: this changed to ...")
and bump `date`. The PR discussion settles it.
