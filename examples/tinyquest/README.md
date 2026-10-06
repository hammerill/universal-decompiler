# Worked example: TinyQuest

A complete, legally clean run of the decompile-any-binary workflow: a small program compiled to a stripped
binary, reversed with Ghidra 12.1.4 through `ud`, and rebuilt as C++17/CMake that prints exactly what the
original prints.

| Folder | What it is |
|---|---|
| [`original/`](original/) | The "original": a tiny C-style game engine (`src/tinyquest.cpp`), its CMake build (optimised, `-fno-inline`, stripped; `/O1` without a PDB on MSVC), and `make_pack.py`, which packs `assets_src/` into `tinyquest.pak`: the dummy asset archive that stands in for "the user's own copy". |
| [`reconstruction/`](reconstruction/) | The decomp repo the workflow produced: `DECOMPLOG.md` (the journal), `DECOMP_PLAN.md` (done criterion, route, module map), C++ with every function's original address, `tools/extract_assets.py` (a PEP 723 script that decodes the archive format it found in the binary), `decomp/progress.json` (`ud funcs`), `ud.toml`. |
| [`run_example.py`](run_example.py) | The end-to-end check CI runs on Windows (MSVC) and Linux (GCC): build the original, make the pack, put both into `data/` of a fresh copy of the decomp repo, extract the assets, `ud build`, `ud run --compare` on seven argument sets, `ud publish check`. |

## Try it
```bash
uv run python examples/tinyquest/run_example.py          # needs CMake, a C++ compiler and uv
```
Or by hand, as a user would:
```bash
cmake -S examples/tinyquest/original -B /tmp/tq-orig -DCMAKE_BUILD_TYPE=Release && cmake --build /tmp/tq-orig --config Release
cp -r examples/tinyquest/reconstruction ~/tinyquest-decomp && cd ~/tinyquest-decomp && git init && mkdir -p data
cp /tmp/tq-orig/bin/tinyquest data/ && python <repo>/examples/tinyquest/original/make_pack.py <repo>/examples/tinyquest/original/assets_src data/tinyquest.pak
uv run tools/extract_assets.py data && ud assets check
ud build && ud run --compare -- --seed 42 --render
```

## How it was made (and what it does and doesn't prove)
The steps in `reconstruction/DECOMPLOG.md` were really run, in order: `ud init`, `ud scan` (ELF x86-64,
GCC 13.3, stripped, no protection), `ud tools check --route native`, Ghidra headless with
`ud/ghidra/ExportFunctions.java` and `DecompileAll.java`, `ud funcs import`, reading the decompiler output
(kept in the gitignored `build/`, never committed), porting module by module, `ud build`, and
`ud run --compare`. Addresses in the comments come from that Linux build; the MSVC build of the original has
different ones.

**Caveat:** the same agent wrote the original program, so this shows that the workflow and the tooling work
end to end. It is not a blind decompilation of unknown code. The original is deliberately small (17 game
functions) so the whole loop fits in a CI run.

No commercial binaries or assets are involved: the original, its assets and the archive format are all ours.
