# Godot

The engine is open source (MIT) and is **not reconstructed**: the deliverable is the game's project,
reopenable in the matching Godot version and exportable for Windows, Linux and macOS. Unlike other vendor engines,
the engine itself is available, so a custom-built engine (modules, patches) can be rebuilt from the
official source if the game needs it.

## Detection signals
A `.pck` with `GDPC` magic next to the executable or appended to it; `ud scan` reads the engine version from
the pack header (e.g. `4.2.1`). C# games also ship `data_<Game>_*/` with .NET assemblies.
An encrypted pack (the export option "encrypt") is a protection: stop unless the user supplies the key
they're entitled to use.

## Route
`engine-project`: `gdre_tools --headless --recover=<game.pck or exe> --output-dir=build/recovered` restores
the project (scenes, resources, GDScript decompiled from bytecode, `project.godot`); open it in the exact
Godot version; C# scripts come from ilspycmd on the game assemblies.

## Required tools (`ud tools check --route godot`)
Git, Python 3.12+, uv, GDRE Tools, Godot (the game's exact version; Mono build for C# games).
Optional: .NET SDK + ilspycmd.

## Deliverable shape
A Godot project folder (`project.godot`, scenes, scripts), with imported assets restored by
`tools/extract_assets.py` (which re-runs GDRE Tools' extraction on the user's copy into a gitignored folder),
export presets for Windows, Linux and macOS, README.

## Known limits
- GDScript bytecode decompiles well but comments and some formatting are gone; Godot 4 tokenised scripts
  and older 3.x bytecode versions differ: use the GDRE release that supports the game's version.
- Imported resources come back as their imported (`.ctex`, `.scn`) forms, sometimes not the original source
  files.
- GDExtension/GDNative native libraries go through the native route.

## Verification approach
Run the original and the exported rebuild from the same save; Godot's `--headless` mode and a test scene
with scripted input make deterministic comparisons possible (`ud run --compare` on printed traces).
