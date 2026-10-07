# Unity (IL2CPP)

Same deliverable as Unity Mono (a project reopenable in the matching editor; the engine is not
reconstructed), with the **documented limits of IL2CPP recovery**: method bodies were compiled to native
code, so C# must be reconstructed from native code.

## Detection signals
`UnityPlayer.dll` + `GameAssembly.dll` (or `.so`) and
`<Game>_Data/il2cpp_data/Metadata/global-metadata.dat` (magic `AF 1B B1 FA`). If the metadata lacks that
magic it is encrypted or obfuscated: `ud scan` stops; that's a protection, don't decrypt it.

## Route
`engine-project`:
1. **Cpp2IL** on the game folder: types, fields, method signatures and RVAs, plus dummy DLLs for ILSpy and
   for AssetRipper's script export. (Il2CppDumper is the older alternative; unmaintained since 2024-08.)
2. **AssetRipper** for scenes, prefabs and assets into a Unity project, using the dummy assemblies.
3. **Ghidra + pyghidra-mcp** on `GameAssembly.dll`: apply the names and signatures from Cpp2IL (its Ghidra
   script output), then reconstruct C# method bodies from the decompiled native code, method by method,
   tracked with `ud funcs` (import Cpp2IL's method list; keys are method names, addresses are RVAs).
4. Open in the exact editor version, compile, build Windows, Linux and macOS players with the Mono or IL2CPP
   backend.

## Required tools (`ud tools check --route unity-il2cpp`)
Git, Python 3.12+, uv, Cpp2IL, AssetRipper, JDK 21+, Ghidra 12.1+, pyghidra-mcp, the Unity editor.
Optional: Il2CppDumper, .NET SDK + ilspycmd (to read the dummy DLLs).

## Deliverable shape
As Unity Mono, plus `decomp/progress.json` tracking reconstructed methods and a list of methods still
stubbed (`throw new NotImplementedException()` with the RVA in a comment).

## Known limits
- Generic sharing, inlining and stripping mean some methods don't exist as separate native functions;
  some engine-code calls are inlined into game code.
- Reconstructed C# is a rewrite, not a decompilation: it can differ in allocation patterns and exception
  behaviour.
- Large games have tens of thousands of methods: prioritise by the vertical slice and by what the done
  criterion needs.

## Verification approach
As Unity Mono; plus per-method checks by comparing logged values from the original (via the native
debugger on the user's offline copy) with the reconstructed method's output.
