# TinyQuest: the original

The program the worked example decompiles. It loads `tinyquest.pak` (a TQPK archive, optionally RLE-packed
entries), plays a scripted run through a maze (`assets_src/level1.map`) with wandering/chasing enemies driven
by an LCG, prints one line per tick, and ends with `result=<outcome> score=<n> hash=<fnv1a>`.

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build --config Release
python make_pack.py assets_src build/bin/data/tinyquest.pak
cd build/bin && ./tinyquest --render          # --seed N --ticks N --inputs UDLR. --data DIR
```
Exit codes: 0 reached the exit, 2 died, 3 ran out of time, 10/11/12 asset errors.

The build mimics a shipped game: optimised, functions kept apart (`-fno-inline`, like many older titles),
every symbol stripped (`-s`; `-Wl,-x` on macOS; no PDB on MSVC), non-PIE on Linux so addresses are stable
between runs (macOS executables are always PIE).
