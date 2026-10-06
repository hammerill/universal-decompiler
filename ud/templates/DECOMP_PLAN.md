# Decompilation plan

## Target
- Binary: `data/<file>` (sha256: <!-- fill in -->)
- Version / edition: <!-- exact build, store, language -->
- Ownership: the user confirmed they own this software on <!-- date -->
- Privacy: the user was reminded on <!-- date --> that this repo stays private (no public remote; the
  pre-push hook enforces it)

## Done criterion (agreed with the user at intake)
<!-- Default proposal; edit it with the user, then keep it fixed. Every item needs evidence in DECOMPLOG.md. -->
- [ ] The CMake project builds on Windows with MSVC as 64-bit
- [ ] The CMake project builds on Linux with GCC or Clang as 64-bit
- [ ] It launches with the assets extracted by `tools/extract_assets.py` from the user's own copy
- [ ] It reaches: <!-- observable state, e.g. "main menu", "first level playable to the first checkpoint" -->
<!-- Vendor-engine families (Unity, Unreal, Godot, GameMaker): the engine is not reconstructed; the criterion is
     "the recovered project opens in <editor version> and builds for Windows and Linux". -->

## Recon (`ud scan`)
- Format / arch / bitness:
- Compiler / toolchain:
- Debug info:
- Engine / family:
- Protections: none found <!-- if any: STOP and tell the user -->

## Prior art
<!-- ud kb search results, community decompilations/tools for this title and engine (current sources), what we reuse -->

## Route and why
- Route: <!-- hybrid-dll | clean-room | static-recomp | managed-decompile | engine-project | script-recovery -->
- Why:
- Tools route: <!-- e.g. native; `ud tools check --route native` -->

## Module map
| Module | Address range / source | Purpose | Status |
|---|---|---|---|

## Third-party libraries identified
| Library | Version | Evidence | Plan (link the open version / reimplement / stub) |
|---|---|---|---|

## Middleware replacement plan
| Original | Replacement | Notes |
|---|---|---|

## Platform layer
- Backend: SDL3 (see the cpp-reconstruction skill's platform-layer reference)
- APIs replaced: <!-- Win32 / D3D9 / DirectInput / DirectSound / console SDK ... -->

## Target layout
```
CMakeLists.txt
src/            reconstructed code, one folder per module, each function with `// 0xADDRESS` of the original
src/platform/   thin platform interface + SDL3 backend
tools/extract_assets.py
decomp/progress.json   (ud funcs)
```
