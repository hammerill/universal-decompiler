# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Extract the assets the rebuilt program needs from YOUR OWN copy of the software into data/.

    uv run tools/extract_assets.py "<path to your install or disc dump>"     # extract
    uv run tools/extract_assets.py --check                                  # what's missing in data/

Nothing copyrighted ships with this repository: this script only reads the copy you own. `--check` exits 0
when every expected file is present, 1 otherwise, and prints one `missing: <path>` line per missing file
(`ud assets check` reads that).
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# Files the rebuilt program loads, relative to data/. Keep this list in sync with the code.
EXPECTED: list[str] = [
    # "models/player.dff",
]


def extract(src: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for rel in EXPECTED:
        s = src / rel
        if s.exists():
            (out / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, out / rel)
    # Formats that need unpacking (archives, packed textures, ...) are decoded here.


def check(out: Path) -> int:
    missing = [rel for rel in EXPECTED if not (out / rel).exists()]
    for rel in missing:
        print(f"missing: {rel}")
    print(f"{len(EXPECTED) - len(missing)}/{len(EXPECTED)} expected files present in {out}")
    return 1 if missing else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", nargs="?", help="your own copy (install folder or extracted disc)")
    ap.add_argument("--out", default="data", help="where the rebuilt program looks for assets (default: data)")
    ap.add_argument("--check", action="store_true", help="only report what's missing")
    a = ap.parse_args()
    out = Path(a.out)
    if a.check:
        return check(out)
    if not a.source:
        ap.error("give the path to your own copy, or --check")
    extract(Path(a.source), out)
    return check(out)


if __name__ == "__main__":
    sys.exit(main())
