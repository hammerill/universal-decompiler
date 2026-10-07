# TinyQuest: local reconstruction

A reconstruction of TinyQuest (universal-decompiler's worked example) made with the decompile-any-binary
workflow. In a real decomp repo this README sits next to code derived from software you own, the repo stays
private, and `data/` (the original and its assets) is never tracked. This one is public only because the
original is our own example program.

## Build
- Windows (MSVC, x64): `cmake -S . -B build -A x64` then `cmake --build build --config Release`
- Linux (GCC or Clang, x86-64): `cmake -S . -B build -DCMAKE_BUILD_TYPE=Release` then `cmake --build build -j`
- macOS (Apple Clang, arm64 or x86-64): the same as Linux
- Or `ud build` (reads `ud.toml`)

The executable lands in `build/bin/tinyquest` (`build\bin\tinyquest.exe` on Windows).

## Assets
The program reads `data/assets/level1.map`, `rules.txt` and `strings.txt`, unpacked from your own copy's
`tinyquest.pak`:
```
uv run tools/extract_assets.py data          # data/ holds your copy: tinyquest(.exe) + tinyquest.pak
uv run tools/extract_assets.py --check       # or: ud assets check
```

## Run
From this folder (so `data/` is found): `build/bin/tinyquest [--seed N] [--ticks N] [--inputs UDLR.] [--render]`.
Compare with the original: `ud run --compare -- --seed 42 --render`.

## Known gaps
- Error messages for a missing or damaged archive differ (the reconstruction reads extracted files); exit
  codes match.
