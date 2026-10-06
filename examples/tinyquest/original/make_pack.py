"""Build tinyquest.pak, the dummy asset pack that plays the role of "the user's own copy" in this example.

    python make_pack.py assets_src out/tinyquest.pak

Format (little-endian), which the reconstruction's tools/extract_assets.py had to work out from the binary:
  header  "TQPK" | u16 version (1) | u16 entry count
  entry   char name[24] (NUL-padded) | u32 offset | u32 stored size | u32 real size | u8 flags | 3 bytes pad
  data    flags & 1: RLE, as (u8 run length 1..255, u8 byte) pairs
"""
import struct
import sys
from pathlib import Path


def rle(data: bytes) -> bytes:
    out, i = bytearray(), 0
    while i < len(data):
        j = i
        while j < len(data) and data[j] == data[i] and j - i < 255:
            j += 1
        out += bytes([j - i, data[i]])
        i = j
    return bytes(out)


def main(src: str, dst: str) -> None:
    files = sorted(p for p in Path(src).iterdir() if p.is_file())
    header = struct.pack("<4sHH", b"TQPK", 1, len(files))
    table_size = 40 * len(files)
    offset = len(header) + table_size
    table, blobs = b"", b""
    for p in files:
        raw = p.read_bytes().replace(b"\r\n", b"\n")
        packed = rle(raw)
        flags, stored = (1, packed) if len(packed) < len(raw) else (0, raw)
        table += struct.pack("<24sIIIB3x", p.name.encode(), offset + len(blobs), len(stored), len(raw), flags)
        blobs += stored
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    Path(dst).write_bytes(header + table + blobs)
    print(f"{dst}: {len(files)} entries")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
