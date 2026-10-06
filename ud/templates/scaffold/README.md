# {name}: local reconstruction

A private, local reconstruction of software I own, made with universal-decompiler. **Not for publication:**
it contains code derived from the original and must never be pushed to a public remote (the pre-push hook
refuses). The original binary and every extracted asset stay in `data/`, which is not tracked.

## Build
- Windows (MSVC, x64): `cmake -S . -B build -A x64` then `cmake --build build --config Release`
- Linux (GCC or Clang, x86-64): `cmake -S . -B build -DCMAKE_BUILD_TYPE=Release` then `cmake --build build -j`
- Or: `ud build --config Release`

## Assets
1. Put your own copy somewhere readable.
2. `uv run tools/extract_assets.py "<path to your copy>"` writes what the program needs into `data/`.
3. `uv run tools/extract_assets.py --check` (or `ud assets check`) lists anything missing.

## Run
`build/bin/game` (Windows: `build\bin\game.exe`), from the repo root so `data/` is found.

## Known gaps
- <!-- what doesn't work yet -->
