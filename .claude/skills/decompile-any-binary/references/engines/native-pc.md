# Native PC (C/C++): any engine without a dedicated route

Covers in-house engines and recognised native engines that have no vendor editor route: RenderWare,
id Tech, Source, Gamebryo/NetImmerse, CryEngine-era titles, Nuitka-compiled Python, and anything `ud scan`
can't place (the fallback for unrecognised binaries).

## Detection signals
- PE/COFF (Windows), ELF (Linux), Mach-O (macOS) without a managed runtime: `ud scan` shows the format,
  arch, Rich header (MSVC toolset), `.comment` (GCC/Clang), PDB path or DWARF, and imports.
- Engine hints: RenderWare strings (`RenderWare Graphics`, `RwEngineOpen`) and `.txd/.dff/.img/.col` files;
  id Tech `.wad/.pk3/.pk4`; Source `gameinfo.txt` + `.vpk` + `tier0.dll`; Gamebryo `.nif` and `NiNode`
  strings; CryEngine `CrySystem.dll`.
- Middleware from imports and strings: Bink, Miles, FMOD, Wwise, Havok, PhysX, Scaleform, Lua, Granny,
  SpeedTree, CRIWARE, D3D8/9/11/12, OpenGL, DirectInput, DirectSound.

## Route
1. **re3-style hybrid** (`hybrid-dll`) for Windows x86/x64 originals that run: a DLL injected into a copy of
   the executable in `data/` replaces functions one by one; the rest of the original is the oracle. Plan
   the switch to a standalone 64-bit build (see `cpp-port.md`).
2. **clean-room rewrite** (`clean-room`) from Ghidra's output for Linux/macOS originals, small programs, or
   once the hybrid has replaced most of the code.
Steps: Ghidra analysis (pyghidra-mcp or headless with `ExportFunctions.java`), `ud funcs import`, module
map from strings/imports/call graph, vertical slice, module by module, platform layer (SDL3), middleware
replacements.

## Required tools (`ud tools check --route native`)
Git, CMake 3.20+, a C++ compiler (MSVC / GCC / Clang), Python 3.12+, uv, JDK 21+, Ghidra 12.1+, pyghidra-mcp.
Optional: Ninja, SDL3 dev files (otherwise fetched by CMake), x64dbg (Windows) or GDB, 7-Zip.

## Deliverable shape
A CMake project: `src/` per module with original addresses in comments, `src/platform/` (SDL3 + headless),
open middleware replacements under `third_party/` or fetched, `tools/extract_assets.py`,
`decomp/progress.json`, README with Windows, Linux and macOS build steps. During the hybrid phase, also the
injectable DLL target.

## Known limits
- Optimised code loses structure (inlining, tail calls, merged functions, LTO); a reconstructed function may
  map to several original addresses or none.
- No symbols: names are yours. A PDB path in `ud scan` doesn't mean the PDB is available; never look for
  leaked ones.
- Middleware with no open equivalent needs a reimplementation of the used subset, which can dominate the
  effort (Scaleform UIs, Havok behaviour). Say so in the plan.
- C++ classes: vtables and RTTI help (MSVC RTTI gives class names even in stripped binaries); templates and
  STL are noise to skip (mark them `skipped` after identifying the library and version).

## Verification approach
- Hybrid: switch a replaced function off/on and compare behaviour in the same session; bisect regressions by
  function.
- Standalone: `ud run --original --shot` vs `ud run --shot` from the same save/scene; scripted input with fixed
  seeds; logged traces (positions, RNG state, score) from both; `ud run --compare` when output is textual.
- Debugger (x64dbg/GDB) on the original to confirm a hypothesis before porting it.
