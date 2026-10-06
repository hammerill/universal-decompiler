# .NET / XNA / FNA / MonoGame

## Detection signals
- PE with a CLR header (`ud scan`: "CLR v4.0.30319", imports only `mscoree.dll`), `*.runtimeconfig.json`,
  a .NET single-file bundle marker, or `FNA.dll`, `MonoGame.Framework.dll`, `Microsoft.Xna.Framework*.dll`,
  `Content/*.xnb`.
- Obfuscators (ConfuserEx, Dotfuscator, .NET Reactor, SmartAssembly, Eazfuscator...) are protections:
  `ud scan` stops. Deobfuscation is a bypass: don't.

## Route
`managed-decompile`: `ilspycmd -p -o build/decompiled <Game>.exe` (and each game DLL) produces C# projects;
move the result into `src/`, make it build with `dotnet build` on Windows and Linux, then fix what the
decompiler got wrong. XNA games move to **FNA** (an open, accurate reimplementation of XNA 4.0) or
MonoGame so they run on Linux; that is the middleware replacement for this family. Native helper DLLs
(P/Invoke) go through the native route.

## Required tools (`ud tools check --route dotnet`)
Git, Python 3.12+, uv, .NET SDK 8+, ilspycmd. Optional: Ghidra + pyghidra-mcp for native DLLs.

## Deliverable shape
A C# solution (`.sln` + `.csproj`) targeting a current .NET LTS, building with `dotnet build -c Release`
on both OSes, FNA/MonoGame referenced (FNA's native libraries per OS), `tools/extract_assets.py` copying
`Content/` from the user's copy into `data/`, README.

## Known limits
- Compiler-generated code (async state machines, iterators, lambdas, `switch` on strings) decompiles into
  correct but awkward C#; ILSpy's settings for the C# language version matter.
- XNA's content pipeline: `.xnb` files load with FNA as they are; rebuilding them from source assets isn't
  needed.
- Mixed-mode assemblies (C++/CLI) need the native route for their native half.
- Windows-only APIs (WinForms, registry, Win32 P/Invoke) need replacements behind a small platform layer.

## Verification approach
Run the original and the rebuilt game side by side from the same save; `ud run --compare` for tools with
text output; unit tests over pure game logic ported from observed original behaviour.
