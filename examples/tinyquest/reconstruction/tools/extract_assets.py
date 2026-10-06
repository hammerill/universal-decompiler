# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Extract TinyQuest's assets from YOUR OWN copy into data/assets/.

    uv run tools/extract_assets.py data            # your copy's folder (holding tinyquest.pak); here: data/
    uv run tools/extract_assets.py --check         # what's missing in data/assets/

The reconstruction loads loose files; the original reads them from tinyquest.pak. This script decodes that
archive (format worked out from the original's archive reader at 0x00401BAC/0x00401A4E, see DECOMPLOG.md):

    header  "TQPK" | u16 version (must be 1) | u16 entry count (at most 16)
    entry   char name[24] (NUL-padded) | u32 offset | u32 stored size | u32 real size | u8 flags | 3 pad bytes
    data    flags & 1: RLE as (u8 run length, u8 byte) pairs, output capped at the real size

`--check` prints `missing: <path>` per missing file and exits 1 if anything is missing (`ud assets check`).
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

PACK = "tinyquest.pak"
EXPECTED = ["assets/level1.map", "assets/rules.txt", "assets/strings.txt"]
ENTRY = struct.Struct("<24sIIIB3x")   # 40 bytes


def read_pack(path: Path) -> dict[str, bytes]:
    blob = path.read_bytes()
    if len(blob) < 8 or blob[:4] != b"TQPK":
        raise SystemExit(f"{path}: not a TinyQuest archive (no TQPK magic)")
    version, count = struct.unpack_from("<HH", blob, 4)
    if version != 1 or count > 16 or 8 + ENTRY.size * count > len(blob):
        raise SystemExit(f"{path}: unsupported archive (version {version}, {count} entries)")
    out = {}
    for i in range(count):
        raw_name, offset, stored, size, flags = ENTRY.unpack_from(blob, 8 + ENTRY.size * i)
        name = raw_name[:23].split(b"\0", 1)[0].decode("ascii")
        if offset + stored > len(blob):
            raise SystemExit(f"{path}: entry {name} points past the end of the file")
        data = blob[offset:offset + stored]
        if flags & 1:
            dec = bytearray()
            for k in range(0, stored - 1, 2):
                dec += bytes([data[k + 1]]) * data[k]
            data = bytes(dec[:size])
        else:
            data = data[:size]
        out[name] = data
    return out


def extract(src: Path, out: Path) -> None:
    pack = src / PACK if src.is_dir() else src
    if not pack.exists():
        raise SystemExit(f"{pack} not found: point this at the folder of your TinyQuest copy")
    files = read_pack(pack)
    (out / "assets").mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (out / "assets" / name).write_bytes(data)
        print(f"extracted assets/{name} ({len(data)} bytes)")


def check(out: Path) -> int:
    missing = [rel for rel in EXPECTED if not (out / rel).exists()]
    for rel in missing:
        print(f"missing: {rel}")
    print(f"{len(EXPECTED) - len(missing)}/{len(EXPECTED)} expected files present in {out}")
    return 1 if missing else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", nargs="?", help="your own copy: its folder, or tinyquest.pak itself")
    ap.add_argument("--out", default="data", help="data folder the rebuilt program reads (default: data)")
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
