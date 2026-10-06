# Unreal Engine 3 / 4 / 5

The engine belongs to Epic Games and is **not reconstructed**. The deliverable is the **best achievable
editor project** for the game's engine version; this playbook is honest about how far that goes.

## Detection signals
- UE4/5: `<Project>/Binaries/Win64/<Project>-Win64-Shipping.exe`, `Content/Paks/*.pak` (+ `.utoc/.ucas` for
  IoStore), the engine version string (`++UE5+Release-5.3`) that `ud scan` reads from the executable.
- UE3: `*.upk`/`*.xxx` packages, `CookedPC*/` folders.
- Anti-cheat (EasyAntiCheat, BattlEye) is common: `ud scan` stops; never inject into it.

## Route
`engine-project`:
1. Dump reflection data from the user's **offline** copy with **RE-UE4SS** (C++/Lua headers, object dumps):
   class, struct, property and function names with their layouts. Only with the user's OK (it's placed next
   to the game), never with anti-cheat present.
2. Export content with **FModel** (Windows) using the engine version; AES keys for encrypted paks are a
   protection: only if the user supplies a key they're entitled to use, otherwise stop.
3. Generate a C++ project skeleton from the reflection dump (UHT-compatible headers), open it in the
   matching Unreal Editor version, and bring in exported assets where the formats allow.
4. **Ghidra + pyghidra-mcp** on the shipping executable for game-module logic (the `UFunction`
   implementations); Blueprint logic comes back only as bytecode and must be rebuilt by hand.

## Required tools (`ud tools check --route unreal`)
Git, Python 3.12+, uv, JDK 21+, Ghidra 12.1+, pyghidra-mcp, the Unreal Editor of the game's version.
Optional: FModel (Windows only), RE-UE4SS (Windows), 7-Zip.

## Deliverable shape
An Unreal project (`.uproject`, `Source/<Game>/` with reconstructed C++ classes, `Config/`), content
re-imported where possible, README stating exactly what is reconstructed and what is placeholder.

## Known limits (state them in DECOMP_PLAN.md)
- Cooked assets don't round-trip into editable editor assets for every type (materials, Blueprints,
  animation graphs); many come back as placeholders.
- Blueprint graphs can't be recovered as graphs; their logic is rewritten in C++ or Blueprint by hand.
- Engine modifications made by the developer (a custom engine fork) are not available.
- Large UE games are years of work; agree a small, observable done criterion (one map, one system).

## Verification approach
Same map, same inputs: original vs rebuilt (screenshots with `ud run --shot`, logs from `Saved/Logs`), plus
the UE4SS dumps compared against the reconstructed classes' reflection data (names, property offsets).
