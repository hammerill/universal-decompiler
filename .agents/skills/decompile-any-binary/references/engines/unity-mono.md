# Unity (Mono)

The engine belongs to Unity Technologies and is **not reconstructed**. The deliverable is the game's own
code and project, reopenable in the matching Unity editor and buildable for Windows and Linux from it.
State this at intake and set the done criterion accordingly.

## Detection signals
`UnityPlayer.dll` (or `.so`), `<Game>_Data/` with `globalgamemanagers`/`data.unity3d`,
`<Game>_Data/Managed/Assembly-CSharp.dll`, no `GameAssembly.dll`. `ud scan` reports the Unity version
(e.g. `2022.3.21f1`) from the data files.

## Route
`engine-project`:
1. AssetRipper on the game folder -> export as a Unity project (scenes, prefabs, assets, and decompiled
   scripts or placeholders).
2. ilspycmd on `Assembly-CSharp.dll` (and the game's other assemblies) for full C# scripts where
   AssetRipper's output needs replacing.
3. Open in the **exact** editor version from `ud scan`; fix compile errors (missing packages, editor-only
   code, plugin DLLs), restore package versions from `Packages/manifest.json` and `ScriptingAssemblies.json`.
4. Build Windows and Linux players from the editor.
Native plugins (`Plugins/x86_64/*.dll`) need Linux equivalents or stubs; that's the native route in
miniature.

## Required tools (`ud tools check --route unity-mono`)
Git, Python 3.12+, uv, AssetRipper, .NET SDK, ilspycmd, the Unity editor of the game's version.

## Deliverable shape
A Unity project folder (`Assets/`, `Packages/`, `ProjectSettings/`) under the decomp repo, with the
extracted art kept out of git: commit only scripts, scenes/prefabs YAML and settings you can legitimately
keep locally; the asset-extraction script re-runs AssetRipper on the user's copy to restore `Assets/`
content into a gitignored location. README: editor version, how to re-extract, how to build both players.

## Known limits
- Shaders come back as decompiled or placeholder shaders; complex ones need manual rewrites.
- Asset Store packages and plugins are third-party code: re-acquire them rather than keeping decompiled copies.
- Exact editor version matters (serialisation formats change between versions).
- AssetRipper's premium edition has features the free one lacks; plan around the free edition.

## Verification approach
Play the original and the rebuilt player from the same save/scene; compare screenshots (`ud run --original
--shot` / `ud run --shot` on the built player), logs (`Player.log`), and scripted scenarios driven from a debug
script in the project.
