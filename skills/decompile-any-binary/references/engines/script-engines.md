# Script engines: RPG Maker, Ren'Py, LÖVE, HTML5/Electron/NW.js, Adobe AIR/Flash

The game logic ships as scripts or bytecode on top of a runtime that isn't reconstructed. The deliverable
is the **recovered source project**. All of these are quick to recover; the work is in making the result
run under a current runtime on Windows, Linux and macOS.

## Detection signals (`ud scan`)
| Engine | Signals |
|---|---|
| RPG Maker MV/MZ | `www/js/rpg_core.js` (MV) or `js/rmmz_core.js` (MZ), NW.js runtime |
| RPG Maker XP/VX/VX Ace | `Game.rgssad`/`.rgss2a`/`.rgss3a` (`RGSSAD` magic), `Data/Scripts.r*data` |
| RPG Maker 2000/2003 | `RPG_RT.exe` + `RPG_RT.ldb` |
| Ren'Py | `renpy/` + `game/`, `game/*.rpa` (`RPA-3.0`), `*.rpyc` (`RENPY RPC2`) |
| LÖVE | `love.dll`, a `.love` zip, or a zip with `main.lua` appended to the exe |
| Electron / NW.js / HTML5 | `resources/app.asar`, `package.nw`, `nw.dll`, `index.html` + JS |
| Adobe AIR / Flash | `META-INF/AIR/application.xml`, `Adobe AIR.dll`, `.swf` (`FWS/CWS/ZWS`) |

## Route (`script-recovery`)
- **RPG Maker MV/MZ:** the project is already plain JS + JSON (`www/` or the root); copy it into a project
  folder that the editor version can open. Encrypted assets (`.rpgmvp`, `.png_`): a protection; stop unless
  the user decides otherwise with their own key.
- **RPG Maker XP/VX/Ace:** unpack the RGSS archive (RPGMakerDecrypter), extract Ruby scripts from
  `Scripts.rvdata2` (Ruby Marshal + zlib). Runs on the original RGSS player or on a maintained open
  implementation (check current mkxp-z status).
- **RPG Maker 2000/2003:** EasyRPG Player is an open-source reimplementation of the runtime: prior art, so
  check it before anything else (step 1 of the loop).
- **Ren'Py:** rpatool extracts `.rpa`; unrpyc turns `.rpyc` into `.rpy` (pick the release matching the Ren'Py
  major version). The project runs on the matching Ren'Py SDK.
- **LÖVE:** the `.love` (or the zip appended to the exe) is a plain zip of Lua sources; run with the same
  LÖVE version.
- **Electron / NW.js:** `asar extract resources/app.asar build/app`; the result is a Node/JS project; pin the
  Electron/NW.js version from `package.json`/the runtime DLLs.
- **AIR / Flash:** JPEXS decompiles ActionScript and exports an editable project; run under the AIR SDK
  (HARMAN maintains it now) or port the logic to an open runtime (e.g. Ruffle can run many SWFs).

## Required tools
`ud tools check --route rpgmaker | renpy | love2d | html5 | flash-air`: 7-Zip, RPGMakerDecrypter, rpatool +
unrpyc, Node.js + @electron/asar, JPEXS + a JDK.

## Deliverable shape
The recovered project folder in `src/` (scripts, data files, project file), a runner setup (which
runtime/SDK version, how to launch on Windows, Linux and macOS), `tools/extract_assets.py` that unpacks media from
the user's copy into a gitignored folder, README.

## Known limits
- Obfuscated or minified JS stays minified (format it; names don't come back).
- Ren'Py games with custom `.rpyc` protections or a modified engine: treat modifications as obfuscation.
- Flash: AIR native extensions (ANEs) are native code; Ruffle doesn't support every AS3 API.

## Verification approach
Same save or start, same inputs, original runtime vs recovered project; screenshots with `ud run --shot`;
script-level logs (console output) compared with `ud run --compare`.
