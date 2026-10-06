---
name: asset-extraction
description: Write tools/extract_assets.py - the single-file `uv run` script with inline PEP 723 dependencies that reads the user's own copy of the software and writes exactly what the rebuilt program needs into data/ - and reverse-engineer the archive and asset formats it needs (pak/wad/bigfile/disc filesystems, compression, textures, audio), proving them with a round trip. Use when the reconstruction needs the original's assets, when an archive format must be decoded, or when the user asks how to get their game data into the rebuilt program.
---

# Asset extraction

Copyrighted assets never enter the repo. The reconstruction ships a script; the user runs it on their own
copy; the rebuilt program loads from `data/` (gitignored).

## The script contract
`tools/extract_assets.py` (the template comes with `ud init --scaffold`; a complete example is
`examples/tinyquest/reconstruction/tools/extract_assets.py`):
- **single file**, runnable with `uv run tools/extract_assets.py ...`, dependencies declared inline (PEP 723):
  ```python
  # /// script
  # requires-python = ">=3.12"
  # dependencies = ["pillow>=10"]
  # ///
  ```
- `uv run tools/extract_assets.py "<path to the user's copy>" [--out data]`: reads only the user's copy
  (install folder, disc dump folder, ROM), writes into `data/`.
- `uv run tools/extract_assets.py --check [--out data]`: light verification: checks that each expected file
  exists, prints `missing: <path>` per missing file, exits 1 if anything is missing. `ud assets check` runs
  this and reports.
- Clear errors: wrong folder, wrong version (check a known file size or hash and say which edition is
  expected), damaged archive.
- The format notes live in the script's docstring.

## Steps
1. List what the rebuilt program loads (from the reconstruction's file-open calls), and keep `EXPECTED` in the
   script in sync with it.
2. Find each asset in the user's copy: loose files are copied; archives are decoded.
3. For an archive or asset format: find the original's reader in Ghidra (xrefs from the file name or
   extension string, or from `fopen`/`CreateFile`) and take the format from it; check community format
   documentation (prior art). Then the round trip in the reverse-engineering skill: parse every file of
   the format, decode to something viewable and look at it.
4. Decide what the program loads: the original's formats (simplest, the program keeps its loaders) or
   converted ones (PNG/WAV/glTF) if the reconstruction's loaders are modern. Converting is part of the
   script, never a committed output.
5. Run it, then `ud assets check`, then run the program.
6. Document in the decomp repo's README: which copy/edition is expected, the command, what `--check` does.

## Formats you'll meet
- Disc filesystems: ISO9660 (7-Zip, `pycdlib`), XDVDFS (extract-xiso), GameCube/Wii (decomp-toolkit; Wii
  partitions are encrypted: the user extracts them themselves).
- Generic containers: zip variants (`zipfile`, check for custom headers), custom pak/wad/bigfile tables
  (header with count + offset table), MPQ, CPK (CRIWARE).
- Compression: zlib/deflate (`zlib`), LZ77/LZSS variants, Yaz0 (Nintendo), RLE, LZO; identify by the reader
  in the binary, not by guessing.
- Textures: DDS/DXT (BCn), console swizzles (PS2 GS, GameCube tiles, Xbox 360 tiled), palettised formats.
- Audio: ADPCM variants, XMA (Xbox 360), VAG (PlayStation), ADX/HCA (CRIWARE; vgmstream decodes most).

## Rules
- Read-only on the user's copy; write only under `data/` (or `--out`).
- Encrypted assets (a key needed to read them) are a protection: stop and tell the user.
- No downloads of game files from anywhere.
