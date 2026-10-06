# Python frozen apps (PyInstaller, py2exe, cx_Freeze)

## Detection signals
- PyInstaller: the `MEI\x0c\x0b\x0a\x0b\x0e` cookie at the end of the exe (`ud scan` reads the Python version
  and DLL from it), `_internal/base_library.zip`.
- py2exe: `PYTHONSCRIPT` resource, `library.zip` + `python3x.dll`.
- cx_Freeze: `lib/library.zip`, `__startup__` modules.
- Nuitka is *not* this family: it compiles Python to C; `ud scan` routes it to native.
- Encrypted PyInstaller archives (the old `--key` option) are a protection: stop.

## Route
`managed-decompile`:
1. Extract: `pyinstxtractor-ng data/App.exe` (or `pyinstxtractor.py`); for py2exe/cx_Freeze unzip the
   library zip.
2. Decompile the `.pyc` files with **PyLingual** (maintained, Python 3.6 to 3.15) and cross-check doubtful
   functions with **pycdc**. uncompyle6/decompyle3 stop at Python 3.8.
3. Rebuild a Python project (`pyproject.toml`, the original's dependencies at the versions found in the
   bundle), run it with the same Python minor version, then on current versions if the done criterion
   asks for it.

## Required tools (`ud tools check --route python-frozen`)
Git, Python 3.12+, uv, pyinstxtractor, PyLingual. Optional: pycdc.

## Deliverable shape
A Python project (`pyproject.toml`, `src/<package>/`), dependency list with versions, data files restored
from the user's copy by `tools/extract_assets.py`, README with `uv run` instructions for Windows and Linux.
"Builds with CMake" doesn't apply here; the done criterion says "runs with uv on both OSes".

## Known limits
- Bytecode decompilation of recent Python versions isn't perfect: PyLingual verifies its output by
  recompiling, pycdc gives a second opinion; some functions need hand-fixing from the disassembly
  (`python -m dis`).
- C extensions (`.pyd`/`.so`) inside the bundle are native code: replace with the upstream package if it's a
  public library, else the native route.

## Verification approach
Original exe vs `uv run` of the rebuilt project with the same inputs; `ud run --compare` on output; pytest on
pure functions with values observed from the original.
