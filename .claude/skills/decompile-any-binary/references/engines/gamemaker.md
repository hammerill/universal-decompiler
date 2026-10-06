# GameMaker

The runner belongs to YoYo Games and is **not reconstructed**; the deliverable is the recovered project, as
far as the tools allow.

## Detection signals
`data.win` (Windows), `game.unx` (Linux), `game.ios`/`game.droid`: an IFF `FORM` file with a `GEN8` chunk;
`ud scan` reports the bytecode version. A runner compiled with YYC (native code, no bytecode in
`data.win`) means GML must be rebuilt from native code: the native route for the logic.

## Route
`engine-project`: **UndertaleModTool** (GUI) or **UndertaleModCli** (agents) opens `data.win`: decompiles
GML code entries, exports sprites, backgrounds, sounds, rooms and objects. Rebuild a GameMaker project
(`.yyp`) from that, or keep a "data.win + exported scripts" project that UndertaleModTool can rebuild.

## Required tools (`ud tools check --route gamemaker`)
Git, Python 3.12+, uv, UndertaleModTool/UndertaleModCli. Optional: the GameMaker IDE.

## Deliverable shape
Recovered GML scripts and object/room definitions under `src/`, a project the IDE can open where the
export is complete, `tools/extract_assets.py` that runs UndertaleModCli's export scripts on the user's
`data.win` into a gitignored folder, README with the IDE/runtime version.

## Known limits
- Decompiled GML is readable but loses local names in some bytecode versions.
- The newest GameMaker versions change the format often; UndertaleModTool support lags behind them.
- YYC builds: no bytecode; very limited recovery.
- Building for Linux needs the IDE's Linux target (and its licence).

## Verification approach
Original runner vs a runner build of the recovered project, same inputs; compare room transitions, score
and logs (`show_debug_message` output) with `ud run --compare` where the game prints them.
