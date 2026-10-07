"""Identify a binary or an install folder: format, architecture, compiler, debug info, middleware, engine,
protections. Ends with ranked routes, the playbook to read and the tools each route needs.

    ud scan data/game.exe              # one file (its folder is used as context: Unity/Unreal layouts etc.)
    ud scan data/                      # an install folder: picks the main executable(s) itself
    ud scan data/rom.z64 --json        # machine-readable, for agents
    ud scan data/game.exe --no-context # only the file itself

Recognises PE/COFF (incl. Rich header -> MSVC version, PDB path), ELF (DWARF, PS2/PSP/PS3 flavours), Mach-O,
XBE, XEX, SELF, DOL/REL, NSO/NRO/NSP/XCI, PS-X EXE, N64/GBA/NDS ROMs, GameCube/Wii/PS1/PS2/PSP/Xbox disc
images, .NET assemblies, JARs, archives and installers; engines: Unity (Mono/IL2CPP), Unreal 3/4/5, Godot,
GameMaker, RPG Maker, Ren'Py, LÖVE, Electron/NW.js/HTML5, Adobe AIR/Flash, Java, PyInstaller/py2exe/cx_Freeze,
XNA/FNA/MonoGame, RenderWare, id Tech, Source, Gamebryo, CryEngine; packers/DRM/anti-cheat.
Anything unrecognised falls back to the native route (Ghidra + pyghidra-mcp).

Exit code 1 when the scan finds a reason to stop (DRM, packer, anti-cheat, encrypted executable): tell the
user, never bypass it. Everything here only reads files.
"""
from __future__ import annotations

import fnmatch
import os
from pathlib import Path

from ud.common import OK, PROBLEM, emit_json, to_posix, usage
from ud.formats import MIDDLEWARE, analyze

MAX_ENTRIES = 50_000
MAX_DEPTH = 6
SKILL = "skills/decompile-any-binary"

# --------------------------------------------------------------------------- families, engines, routes

# family key: (label, playbook, deliverable)
FAMILIES = {
    "native": ("Native PC (C/C++)", "native-pc.md", "re3-style C++17/CMake reconstruction"),
    "dotnet": (".NET / XNA / FNA / MonoGame", "dotnet.md", "C# solution that builds with `dotnet` on Windows, Linux and macOS"),
    "unity-mono": ("Unity (Mono)", "unity-mono.md", "project reopenable in the matching Unity editor version"),
    "unity-il2cpp": ("Unity (IL2CPP)", "unity-il2cpp.md", "project reopenable in the matching Unity editor, with IL2CPP's recovery limits"),
    "unreal": ("Unreal Engine 3/4/5", "unreal.md", "best achievable editor project; limits stated honestly"),
    "godot": ("Godot", "godot.md", "project reopenable in the matching Godot version"),
    "gamemaker": ("GameMaker", "gamemaker.md", "recovered GameMaker project as far as the tools allow"),
    "rpgmaker": ("RPG Maker", "script-engines.md", "recovered RPG Maker project"),
    "renpy": ("Ren'Py", "script-engines.md", "recovered Ren'Py project (.rpy sources)"),
    "love2d": ("LÖVE (Lua)", "script-engines.md", "recovered LÖVE project (Lua sources)"),
    "html5": ("HTML5 / Electron / NW.js", "script-engines.md", "recovered web project (JS/HTML sources)"),
    "flash-air": ("Adobe AIR / Flash", "script-engines.md", "recovered ActionScript project"),
    "java": ("Java (LWJGL etc.)", "java.md", "Gradle or Maven project"),
    "python-frozen": ("Python frozen app (PyInstaller, py2exe, cx_Freeze)", "python-frozen.md", "Python project"),
    "n64": ("Nintendo 64", "consoles.md", "C++/CMake PC port with a platform layer replacing the console SDK"),
    "gba": ("Game Boy Advance", "consoles.md", "C++/CMake PC port with a platform layer replacing the hardware"),
    "nds": ("Nintendo DS", "consoles.md", "C++/CMake PC port with a platform layer replacing the hardware"),
    "ps1": ("PlayStation", "consoles.md", "C++/CMake PC port with a platform layer replacing PsyQ/hardware"),
    "ps2": ("PlayStation 2", "consoles.md", "C++/CMake PC port with a platform layer replacing the PS2 SDK/hardware"),
    "psp": ("PlayStation Portable", "consoles.md", "C++/CMake PC port with a platform layer replacing the PSP SDK"),
    "gamecube-wii": ("GameCube / Wii", "consoles.md", "C++/CMake PC port with a platform layer replacing the Dolphin SDK/GX"),
    "xbox": ("Original Xbox", "consoles.md", "C++/CMake PC port with a platform layer replacing the XDK"),
    "xbox360": ("Xbox 360", "consoles.md", "C++/CMake PC port with a platform layer replacing the XDK"),
    "ps3": ("PlayStation 3", "consoles.md", "C++/CMake PC port with a platform layer replacing the PS3 SDK"),
    "switch": ("Nintendo Switch", "consoles.md", "C++/CMake PC port with a platform layer replacing the NX SDK"),
}
CONSOLES = {"n64", "gba", "nds", "ps1", "ps2", "psp", "gamecube-wii", "xbox", "xbox360", "ps3", "switch"}
EDITOR_FAMILIES = {"unity-mono", "unity-il2cpp", "unreal", "godot", "gamemaker"}

# engine key: (label, family)
ENGINES = {
    "unity-mono": ("Unity (Mono)", "unity-mono"), "unity-il2cpp": ("Unity (IL2CPP)", "unity-il2cpp"),
    "unreal-3": ("Unreal Engine 3", "unreal"), "unreal": ("Unreal Engine 4/5", "unreal"),
    "godot": ("Godot", "godot"), "gamemaker": ("GameMaker", "gamemaker"),
    "rpgmaker-mvmz": ("RPG Maker MV/MZ (NW.js)", "rpgmaker"), "rpgmaker-rgss": ("RPG Maker XP/VX/VX Ace (RGSS)", "rpgmaker"),
    "rpgmaker-2k": ("RPG Maker 2000/2003", "rpgmaker"), "renpy": ("Ren'Py", "renpy"), "love2d": ("LÖVE", "love2d"),
    "electron": ("Electron", "html5"), "nwjs": ("NW.js", "html5"), "html5": ("HTML5 (browser runtime)", "html5"),
    "air": ("Adobe AIR", "flash-air"), "flash": ("Flash (SWF)", "flash-air"), "java": ("Java", "java"),
    "pyinstaller": ("Python (PyInstaller)", "python-frozen"), "py2exe": ("Python (py2exe)", "python-frozen"),
    "cx_freeze": ("Python (cx_Freeze)", "python-frozen"), "nuitka": ("Python compiled to C by Nuitka", "native"),
    "xna-fna": ("XNA / FNA / MonoGame (.NET)", "dotnet"), "dotnet": (".NET application", "dotnet"),
    "renderware": ("RenderWare", "native"), "idtech": ("id Tech", "native"), "source": ("Source", "native"),
    "gamebryo": ("Gamebryo / NetImmerse", "native"), "cryengine": ("CryEngine", "native"),
    "native": ("unknown native engine (in-house or unrecognised)", "native"),
    **{c: (FAMILIES[c][0], c) for c in CONSOLES},
}

METHODS = {
    "hybrid-dll": "re3-style hybrid: reimplemented functions injected into the original executable via a DLL, so the program runs at every step",
    "clean-room": "clean-room rewrite from decompiler output, module by module",
    "static-recomp": "static recompilation with a mature recompiler, then a native runtime/platform layer",
    "managed-decompile": "decompile to a source project, then fix it until it builds and runs",
    "engine-project": "recover the game's own project for the matching engine editor (the vendor engine is not reconstructed)",
    "script-recovery": "unpack the archive and recover the scripts and project files",
}


def routes_for(family: str, main: dict | None) -> list[dict]:
    fam_label, playbook, deliverable = FAMILIES[family]
    r = []

    def add(method, tools_route, why):
        r.append(dict(method=method, description=METHODS[method], family=family, tools_route=tools_route,
                      playbook=f"{SKILL}/references/engines/{playbook}", deliverable=deliverable, why=why))

    if family == "native":
        win32 = bool(main) and main["format"].startswith("PE") and main.get("arch") in ("x86", "x86-64") and not main.get("dll")
        if win32:
            add("hybrid-dll", "native", "Windows x86/x64 executable: inject reimplemented functions and keep the original runnable")
        add("clean-room", "native", "always possible; needed for non-Windows originals")
    elif family in ("dotnet", "java", "python-frozen"):
        add("managed-decompile", family, "managed code decompiles to near-source")
    elif family in EDITOR_FAMILIES:
        add("engine-project", family, "the engine belongs to its vendor; recover the game's code and project")
    elif family in ("rpgmaker", "renpy", "love2d", "html5", "flash-air"):
        add("script-recovery", family, "the game logic ships as scripts or bytecode")
    elif family == "n64":
        add("static-recomp", "n64-recomp", "N64Recomp is mature and gives a running native build quickly")
        add("clean-room", "n64", "splat + Ghidra when recompilation doesn't fit (or as a follow-up)")
    elif family == "xbox360":
        add("static-recomp", "xbox360-recomp", "XenonRecomp exists for Xbox 360 PowerPC")
        add("clean-room", "xbox360", "Ghidra (XEX loader) + rewrite")
    elif family == "ps2":
        add("clean-room", "ps2", "splat + Ghidra (EE plugin); PS2 recompilers are still experimental")
        add("static-recomp", "ps2-recomp", "PS2Recomp, if the game is within what it currently handles")
    else:
        add("clean-room", family, f"{fam_label}: Ghidra with the platform loader, then a rewrite over a platform layer")
    try:
        from ud.tools import route_tools
        for x in r:
            x["tools"] = route_tools(x["tools_route"])
    except (ImportError, KeyError, OSError):
        pass
    return r


# --------------------------------------------------------------------------- folder index


class Index:
    """Bounded, lowercase index of an install folder (relative posix paths)."""

    def __init__(self, root: Path, max_entries: int = MAX_ENTRIES, max_depth: int = MAX_DEPTH):
        self.root = root
        self.files: dict[str, str] = {}
        self.sizes: dict[str, int] = {}
        self.dirs: set[str] = set()
        self.truncated = False
        n = 0
        for dirpath, dirnames, filenames in os.walk(root):
            rel = Path(dirpath).relative_to(root).as_posix()
            depth = 0 if rel == "." else rel.count("/") + 1
            dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules", "__pycache__")] if depth < max_depth else []
            for d in dirnames:
                self.dirs.add((d if rel == "." else f"{rel}/{d}").lower())
            for fn in filenames:
                r = fn if rel == "." else f"{rel}/{fn}"
                self.files[r.lower()] = r
                try:
                    self.sizes[r.lower()] = os.stat(os.path.join(dirpath, fn)).st_size
                except OSError:
                    self.sizes[r.lower()] = 0
                n += 1
                if n >= max_entries:
                    self.truncated = True
                    return

    def find(self, *patterns: str) -> list[str]:
        pats = [p.lower() for p in patterns]
        return [f for f in self.files if any(fnmatch.fnmatchcase(f, p) for p in pats)]

    def has(self, *patterns: str) -> bool:
        pats = [p.lower() for p in patterns]
        return any(fnmatch.fnmatchcase(f, p) for f in self.files for p in pats)

    def has_dir(self, *patterns: str) -> bool:
        pats = [p.lower() for p in patterns]
        return any(fnmatch.fnmatchcase(d, p) for d in self.dirs for p in pats)

    def path(self, rel: str) -> Path:
        return self.root / self.files.get(rel, rel)


ANTI_CHEAT = [
    ("EasyAntiCheat", ("easyanticheat/*", "*easyanticheat*", "start_protected_game.exe")),
    ("BattlEye", ("battleye/*", "*beservice*", "*_be.exe")),
    ("EA Javelin anticheat", ("eaanticheat*", "*/eaanticheat*")),
    ("nProtect GameGuard", ("gameguard/*", "*gamemon*.des")),
    ("XIGNCODE3", ("xigncode/*", "*x3.xem")),
    ("Tencent ACE", ("*ace-base*", "*sgguard*")),
    ("mhyprot", ("*mhypbase.dll", "*mhyprot*")),
    ("PunkBuster", ("pb/pbsvc*", "pb/pbcl*")),
]
HELPER_EXES = ("unins", "uninst", "setup", "crash", "report", "launcher", "redist", "vcredist", "vc_redist", "dxsetup",
               "dotnet", "unitycrashhandler", "easyanticheat", "start_protected_game", "ue4prereq", "cefsharp", "notification_helper",
               "steamerrorreporter", "quicksfv", "touchup", "update", "patch")
EXEC_PATTERNS = ("*.exe", "*.xbe", "*.xex", "*.dol", "*.elf", "*.self", "*.nso", "*.nro", "*.z64", "*.n64", "*.v64", "*.gba", "*.nds",
                 "*.iso", "*.gcm", "*.rvz", "*.wbfs", "*.cso", "*.bin", "*.x86_64", "*.x86", "*.jar", "*.swf", "*.love", "*.apk",
                 "*.ps-x", "*.psexe", "eboot.bin", "eboot.elf", "eboot.pbp", "main", "default.xbe", "default.xex", "*.dll", "*.so")


def candidate_binaries(ix: Index) -> list[str]:
    """Most likely main executables first."""
    def score(rel: str) -> tuple:
        name = rel.rsplit("/", 1)[-1]
        depth = rel.count("/")
        helper = any(h in name for h in HELPER_EXES)
        primary = name in ("default.xbe", "default.xex", "main", "main.dol", "eboot.bin", "eboot.elf") or name.endswith(
            ("-win64-shipping.exe", "-wingdk-shipping.exe"))
        dll = name.endswith((".dll", ".so"))
        return (not primary, helper, dll, depth, -ix.sizes.get(rel, 0))
    cands = [f for f in ix.find(*EXEC_PATTERNS) if ix.sizes.get(f, 0) > 512]
    # Unity: the exe next to <Name>_Data
    datas = {d.rsplit("/", 1)[-1][:-5] for d in ix.dirs if d.endswith("_data")}
    cands.sort(key=lambda f: (f.rsplit("/", 1)[-1].rsplit(".", 1)[0] not in datas, *score(f)))
    if not cands:
        cands = sorted((f for f in ix.files if ix.sizes.get(f, 0) > 4096), key=lambda f: -ix.sizes.get(f, 0))[:5]
    return cands


# --------------------------------------------------------------------------- detection

def detect_folder(ix: Index) -> list[tuple[str, int, list[str], dict]]:
    """Engine signals from the folder layout: [(engine_key, score, evidence, details)]."""
    hits: list[tuple[str, int, list[str], dict]] = []

    def add(key, score, ev, **det):
        hits.append((key, score, ev, det))

    # Unity
    datas = sorted({f.rsplit("/", 1)[0] for f in ix.find("*_data/globalgamemanagers", "*_data/data.unity3d", "*_data/mainData")})
    if ix.has("*unityplayer.dll", "*unityplayer.so", "*unityplayer.dylib") or datas:
        det: dict = {"data_dir": ix.files.get(datas[0], datas[0]) if datas else None}
        if datas:
            det["unity_version"] = unity_version(ix, datas[0])
        meta = ix.find("*il2cpp_data/metadata/global-metadata.dat")
        if ix.has("*gameassembly.dll", "*gameassembly.so", "*gameassembly.dylib") or meta:
            if meta:
                with open(ix.path(meta[0]), "rb") as fh:
                    det["metadata_magic_ok"] = fh.read(4) == b"\xaf\x1b\xb1\xfa"
            add("unity-il2cpp", 100, ["UnityPlayer + GameAssembly / global-metadata.dat"], **det)
        else:
            add("unity-mono", 100, ["UnityPlayer + Managed/Assembly-CSharp.dll" if ix.has("*_data/managed/assembly-csharp.dll") else "UnityPlayer"], **det)
    # Unreal 4/5 and 3
    shipping = ix.find("*/binaries/win64/*-win64-shipping.exe", "*/binaries/win64/*-wingdk-shipping.exe", "*/binaries/linux/*-linux-shipping")
    if shipping or ix.has("*/content/paks/*.pak", "*/content/paks/*.utoc") or ix.has_dir("engine/binaries/thirdparty"):
        add("unreal", 100 if shipping else 75, [ix.files[shipping[0]] if shipping else "Content/Paks"], project=shipping[0].split("/")[0] if shipping else None)
    if ix.has("*.upk", "*/cookedpc/*", "*/cookedpcconsole/*", "*/cookedwin*/*", "*.xxx") and not shipping:
        add("unreal-3", 90, ix.find("*.upk", "*/cookedpc*/*")[:2])
    # Godot
    for p in ix.find("*.pck")[:3]:
        with open(ix.path(p), "rb") as fh:
            if fh.read(4) == b"GDPC":
                add("godot", 100, [ix.files[p]])
                break
    # GameMaker
    for name in ("data.win", "game.unx", "game.ios", "game.droid", "assets/game.unx"):
        if name in ix.files:
            add("gamemaker", 100, [ix.files[name]])
            break
    # RPG Maker
    if ix.has("www/js/rpg_core.js", "js/rpg_core.js"):
        add("rpgmaker-mvmz", 100, ["rpg_core.js (MV)"], version="MV")
    elif ix.has("js/rmmz_core.js", "www/js/rmmz_core.js"):
        add("rpgmaker-mvmz", 100, ["rmmz_core.js (MZ)"], version="MZ")
    if ix.has("game.rgssad", "game.rgss2a", "game.rgss3a", "data/scripts.rxdata", "data/scripts.rvdata", "data/scripts.rvdata2"):
        add("rpgmaker-rgss", 100, ix.find("game.rgss*", "data/scripts.r*")[:2])
    if ix.has("rpg_rt.exe") and ix.has("rpg_rt.ldb", "*.ldb"):
        add("rpgmaker-2k", 100, ["RPG_RT.exe + RPG_RT.ldb"])
    # Ren'Py
    if ix.has_dir("renpy") and ix.has_dir("game") or ix.has("game/*.rpa", "game/*.rpyc", "*/game/*.rpyc"):
        add("renpy", 100, ["renpy/ + game/" if ix.has_dir("renpy") else "game/*.rpa|*.rpyc"])
    # LÖVE
    if ix.has("love.dll", "*.love", "lovec.exe"):
        add("love2d", 95, ix.find("love.dll", "*.love")[:1])
    # Electron / NW.js / HTML5
    if ix.has("resources/app.asar", "resources/app/package.json", "*/resources/app.asar"):
        add("electron", 95, ix.find("resources/app.asar", "resources/app/package.json", "*/resources/app.asar")[:1])
    elif ix.has("package.nw", "nw.dll", "*/nw.dll", "nw_elf.dll"):
        add("nwjs", 95, ix.find("package.nw", "nw.dll", "nw_elf.dll")[:1])
    elif ix.has("index.html") and ix.has("*.js"):
        add("html5", 55, ["index.html + js"])
    # Adobe AIR / Flash
    if ix.has("meta-inf/air/application.xml", "*/meta-inf/air/application.xml", "adobe air/*", "*/adobe air.dll"):
        add("air", 100, ix.find("meta-inf/air/application.xml", "*/meta-inf/air/application.xml", "*adobe air*")[:1])
    elif ix.has("*.swf"):
        add("flash", 80, ix.find("*.swf")[:2])
    # Java
    jars = ix.find("*.jar")
    if jars and (ix.has_dir("jre", "jre/*", "jdk*", "java*", "runtime") or len(jars) <= 8):
        add("java", 70, [ix.files[j] for j in jars[:2]])
    # Python frozen
    if ix.has("base_library.zip", "_internal/base_library.zip", "*/_internal/base_library.zip"):
        add("pyinstaller", 95, ix.find("*base_library.zip")[:1])
    elif ix.has("lib/library.zip") and ix.has("python3*.dll", "lib/python3*.dll", "*.zip"):
        add("cx_freeze", 85, ["lib/library.zip"])
    elif ix.has("library.zip") and ix.has("python*.dll"):
        add("py2exe", 85, ["library.zip + python*.dll"])
    # .NET / XNA / FNA / MonoGame
    if ix.has("fna.dll", "monogame.framework.dll", "microsoft.xna.framework*.dll", "*/fna.dll") or ix.has("content/*.xnb"):
        add("xna-fna", 95, (ix.find("fna.dll", "monogame.framework.dll", "microsoft.xna.framework*.dll") or ["Content/*.xnb"])[:2])
    elif ix.find("*.runtimeconfig.json") and not ix.has("*unityplayer*"):
        add("dotnet", 70, ix.find("*.runtimeconfig.json")[:1])
    # native engines
    if ix.has("*.txd", "*.dff") and ix.has("*.img", "*.col", "*.ifp"):
        add("renderware", 85, ix.find("*.txd", "*.dff")[:2])
    if ix.has("*.wad", "*.pk3", "base/*.pk4", "id1/pak0.pak", "base/*.resources"):
        add("idtech", 70, ix.find("*.wad", "*.pk3", "base/*.pk4", "id1/pak0.pak")[:2])
    if ix.has("*/gameinfo.txt") and ix.has("*_dir.vpk", "bin/engine.dll", "bin/x64/engine.dll"):
        add("source", 90, ix.find("*/gameinfo.txt")[:1])
    if ix.has("*.nif") or (ix.has("data/*.bsa") and ix.has("data/*.esm", "data/*.esp")):
        add("gamebryo", 80, ix.find("*.nif", "data/*.bsa")[:1])
    if ix.has("*crysystem.dll"):
        add("cryengine", 95, ix.find("*crysystem.dll")[:1])
    # console layouts (extracted discs / exefs)
    if ix.has("ps3_game/usrdir/eboot.bin", "*/ps3_game/usrdir/eboot.bin", "usrdir/eboot.bin"):
        add("ps3", 95, ["PS3_GAME/USRDIR/EBOOT.BIN"])
    if ix.has("psp_game/sysdir/eboot.bin", "*/psp_game/sysdir/eboot.bin"):
        add("psp", 95, ["PSP_GAME/SYSDIR/EBOOT.BIN"])
    if ix.has("system.cnf") and ix.has("sl??_???.??", "sc??_???.??", "sl??_???.??;1"):
        with open(ix.path("system.cnf"), "rb") as fh:
            cnf = fh.read(512)
        add("ps2" if b"BOOT2" in cnf else "ps1", 95, ["SYSTEM.CNF + " + ix.files[ix.find("sl??_???.??", "sc??_???.??")[0]]])
    if ix.has("default.xbe", "*/default.xbe"):
        add("xbox", 95, ["default.xbe"])
    if ix.has("default.xex", "*/default.xex"):
        add("xbox360", 95, ["default.xex"])
    if ix.has("main.npdm", "*/main.npdm", "exefs/main"):
        add("switch", 95, ix.find("main.npdm", "*/main.npdm", "exefs/main")[:1])
    if ix.has("sys/main.dol", "*/sys/main.dol", "*.dol"):
        add("gamecube-wii", 90, ix.find("sys/main.dol", "*/sys/main.dol", "*.dol")[:1])
    return hits


def unity_version(ix: Index, data_dir: str) -> str | None:
    import re
    for name in ("globalgamemanagers", "data.unity3d", "mainData"):
        rel = f"{data_dir}/{name}".lower()
        if rel in ix.files:
            try:
                with open(ix.path(rel), "rb") as fh:
                    m = re.search(rb"(?:20[1-3][0-9]|6000|5|4|3)\.[0-9]+\.[0-9]+[abfpx][0-9]+", fh.read(1 << 16))
                if m:
                    return m.group(0).decode()
            except OSError:
                pass
    return None


def detect_binary(info: dict) -> list[tuple[str, int, list[str], dict]]:
    """Engine/family signals from one analysed binary."""
    hits: list[tuple[str, int, list[str], dict]] = []

    def add(key, score, ev, **det):
        hits.append((key, score, ev, det))

    fmt = info["format"]
    if info.get("platform") in CONSOLES:
        add(info["platform"], 100, [fmt])
    hint = info.get("family_hint")
    if hint:
        key = {"html5": "electron", "flash-air": "air" if "AIR" in fmt else "flash", "rpgmaker": "rpgmaker-rgss",
               "python-frozen": "pyinstaller"}.get(hint, hint)
        add(key, 95, [fmt])
    for p in info.get("appended", []):
        h = p.get("family_hint")
        if h == "python-frozen":
            add("pyinstaller" if p["kind"] == "pyinstaller" else "py2exe", 100, [f"{p['kind']} payload" + (f" (Python {p['python']})" if p.get("python") else "")],
                python=p.get("python"))
        elif h:
            add(h, 100, [f"{p['kind']} payload"])
    imports = [x.lower() for x in info.get("imports", []) + info.get("needed", [])]
    if any(x.startswith("unityplayer") for x in imports):
        add("unity-mono", 80, ["imports UnityPlayer"])
    if info.get("managed"):
        add("dotnet", 85, [f".NET assembly (CLR {info.get('clr_version', '?')})"])
    if info.get("dotnet_bundle"):
        add("dotnet", 90, [".NET single-file bundle"])
    strings = dict(info.get("_strings", {}).get("engine", []))
    mapping = {"unreal": ("unreal", 70), "idtech": ("idtech", 50), "source": ("source", 60), "cryengine": ("cryengine", 70),
               "renderware": ("renderware", 75), "gamebryo": ("gamebryo", 70), "xna-fna": ("xna-fna", 90), "godot": ("godot", 60),
               "electron": ("electron", 70), "nwjs": ("nwjs", 70), "air": ("air", 70)}
    for k, (eng, score) in mapping.items():
        if k in strings:
            if eng == "xna-fna" and not info.get("managed"):
                continue
            add(eng, score, [f"string {strings[k]!r}"])
    comp = dict(info.get("_strings", {}).get("compiler", []))
    if "Nuitka (Python compiled to C)" in comp:
        add("nuitka", 80, ["Nuitka strings"])
    if "python" in strings and not any(h[0] in ("pyinstaller", "py2exe", "cx_freeze") for h in hits):
        s = strings["python"]
        add("py2exe" if "py2exe" in s or "PYTHONSCRIPT" in s else "cx_freeze" if "cx_Freeze" in s or "__startup__" in s else "pyinstaller",
            70, [f"string {s!r}"])
    return hits


def compilers(info: dict) -> list[dict]:
    out = []
    if info.get("rich"):
        out.append(dict(name="Microsoft Visual C++", version=info["rich"], confidence=95, evidence="Rich header"))
    for c in info.get("comment", []):
        out.append(dict(name="GCC" if "GCC" in c else "Clang/LLVM" if "clang" in c.lower() else c.split()[0], version=c, confidence=95,
                        evidence="ELF .comment"))
    for name, hit in info.get("_strings", {}).get("compiler", []):
        if name.startswith("Microsoft Visual C++") and out and out[0]["name"] == "Microsoft Visual C++":
            continue
        if any(o["name"] == name for o in out):
            continue
        out.append(dict(name=name, version=hit if name in ("GCC", "Clang/LLVM") else None, confidence=70, evidence=f"string {hit!r}"))
    if info.get("managed"):
        out.append(dict(name=".NET compiler (C#/VB/F#)", version=info.get("clr_version"), confidence=90, evidence="CLR header"))
    fmt = info["format"]
    if not out and (fmt.startswith("DOL") or fmt.startswith("REL")):
        out.append(dict(name="Metrowerks CodeWarrior (typical for GameCube/Wii)", version=None, confidence=40, evidence="platform default"))
    return out


def debug_info(info: dict) -> dict:
    d = {}
    if info.get("pdb"):
        d["pdb_path"] = info["pdb"]
    if info.get("dwarf"):
        d["dwarf"] = True
    if info.get("symtab"):
        d["symbol_table"] = "ELF .symtab"
    if info.get("nsyms"):
        d["symbol_table"] = f"Mach-O LC_SYMTAB ({info['nsyms']} symbols)"
    if info.get("has_symbols_table"):
        d["symbol_table"] = "COFF symbol table"
    if info.get("debug_filename"):
        d["xbe_debug_filename"] = info["debug_filename"]
    if info.get("managed"):
        d["metadata"] = ".NET metadata (type and member names survive unless obfuscated)"
    return d


def middleware(info: dict) -> list[dict]:
    import re
    out = []
    imports = info.get("imports", []) + info.get("needed", []) + info.get("dylibs", [])
    strings = dict(info.get("_strings", {}).get("middleware", []))
    for name, _, imp_rx, repl in MIDDLEWARE:
        ev = []
        if name in strings:
            ev.append(f"string {strings[name]!r}")
        if imp_rx:
            m = [i for i in imports if re.search(imp_rx, i.rsplit("/", 1)[-1].lower())]
            if m:
                ev.append("imports " + ", ".join(m[:3]))
        if ev:
            out.append(dict(name=name, confidence=90 if any(e.startswith("imports") for e in ev) else 70, evidence="; ".join(ev),
                            replacement=repl))
    return out


def protections(info: dict) -> list[dict]:
    out = list(info.get("_protections", []))
    for name, hit in info.get("_strings", {}).get("dotnet_protector", []):
        if info.get("managed"):
            out.append(dict(name=f"{name} (.NET obfuscator)", kind="obfuscator", confidence=80, evidence=f"string {hit!r}"))
    from ud.formats import PROTECTOR_STRINGS
    kinds = {n: (k, c) for n, _, k, c in PROTECTOR_STRINGS}
    for name, hit in info.get("_strings", {}).get("protector", []):
        if any(name.split("/")[0] in p["name"] for p in out):
            continue
        k, c = kinds[name]
        out.append(dict(name=name, kind=k, confidence=c, evidence=f"string {hit!r}"))
    return out


# --------------------------------------------------------------------------- scan

def scan(target: str, context: bool = True, deep: bool = True) -> dict:
    root = Path(to_posix(target)).expanduser()
    if not root.exists():
        usage(f"no such file or folder: {target}")
    kind = "folder" if root.is_dir() else "file"
    ix = None
    if kind == "folder":
        ix = Index(root)
        cands = [ix.path(c) for c in candidate_binaries(ix)[:3]]
    else:
        cands = [root]
        parent = root.parent.resolve()
        if context and parent != Path(parent.anchor) and parent != Path.home():
            ix = Index(parent, max_entries=20_000, max_depth=4)
    binaries = []
    for i, c in enumerate(cands):
        try:
            binaries.append(analyze(c, deep=deep and i == 0))
        except OSError as e:
            binaries.append(dict(path=str(c), format="unreadable", error=str(e)))
    main = binaries[0] if binaries else None

    hits = detect_folder(ix) if ix else []
    for b in binaries[:1]:
        hits += detect_binary(b)
    if ix and kind == "file" and main and main.get("platform") is None:
        # a lone file in a shared folder: don't let unrelated siblings outrank what the file itself says
        hits = [(k, s - 15 if not any(k == h[0] for h in detect_binary(main)) else s, e, d) for k, s, e, d in hits]
    merged: dict[str, tuple[int, list[str], dict]] = {}
    for k, s, e, d in hits:
        if k in merged:
            ps, pe, pd = merged[k]
            merged[k] = (max(ps, s) + 5, pe + e, {**pd, **{a: b for a, b in d.items() if b is not None}})
        else:
            merged[k] = (s, list(e), {a: b for a, b in d.items() if b is not None})
    ranked = sorted(merged.items(), key=lambda kv: -kv[1][0])
    # specific engines beat generic ones that every Unity/XNA game also triggers
    if ranked and ranked[0][0] == "dotnet" and any(k in merged for k in ("xna-fna", "unity-mono", "unity-il2cpp")):
        ranked.sort(key=lambda kv: kv[0] == "dotnet")
    if ranked and ranked[0][0] == "unity-mono" and "unity-il2cpp" in merged:
        ranked.sort(key=lambda kv: kv[0] != "unity-il2cpp")
    if not ranked:
        ranked = [("native", (30 if main and main["format"] != "unknown" else 10, ["no engine-specific signature"], {}))]
    ekey, (escore, eev, edet) = ranked[0]
    elabel, family = ENGINES[ekey]

    mids = middleware(main) if main else []
    prots = protections(main) if main else []
    if ix:
        for name, pats in ANTI_CHEAT:
            if ix.has(*pats) or ix.has_dir(*[p[:-2] for p in pats if p.endswith("/*")]):
                prots.append(dict(name=name, kind="anti-cheat", confidence=90, evidence="files in the install folder"))
    if family == "unity-il2cpp" and edet.get("metadata_magic_ok") is False:
        prots.append(dict(name="encrypted/obfuscated IL2CPP metadata", kind="obfuscator", confidence=85,
                          evidence="global-metadata.dat has no AF 1B B1 FA magic"))
    blocking = [p for p in prots if p["confidence"] >= 60]
    comp = compilers(main) if main else []
    dbg = debug_info(main) if main else {}

    warnings, stop = [], None
    if blocking:
        names = ", ".join(sorted({p["name"] for p in blocking}))
        stop = dict(reason="protected", protections=names,
                    tell_the_user=(f"The binary is protected ({names}). universal-decompiler never bypasses DRM, packers, anti-cheat, "
                                   "obfuscation or encryption. Options: an unprotected edition you own (e.g. GOG, an older "
                                   "disc release, a DRM-free patch from the publisher), or an executable you decrypted yourself "
                                   "from your own console with your own keys."))
    if main:
        if main.get("installer"):
            warnings.append(f"{main['path']} is an installer ({main['installer']}): install the software (or ask the user to), then scan the installed folder")
        if main.get("archive") or main.get("container"):
            warnings.append(f"{main['path']} is a container ({main['format']}): extract the main executable into data/ first "
                            "(ask the user before extracting anything large)")
        if main.get("strings_truncated"):
            warnings.append("only the first 96 MiB were searched for compiler/middleware strings")
        if main.get("bits") == 32 and family == "native":
            warnings.append("32-bit original: the release target is 64-bit; a 32-bit build is allowed only as an intermediate step "
                            "(e.g. DLL injection)")
    if family in EDITOR_FAMILIES:
        warnings.append(f"{FAMILIES[family][0]}: the engine belongs to its vendor and is not reconstructed. Tell the user at intake; the "
                        "deliverable is the game's own code and project, buildable for Windows, Linux and macOS through that engine.")
    if ix and ix.truncated:
        warnings.append("file index truncated (huge folder): pass a subfolder or the executable for detail")
    if ekey == "rpgmaker-2k":
        warnings.append("RPG Maker 2000/2003: EasyRPG Player is an open-source reimplementation of the runtime; check it first (prior art)")

    routes = routes_for(family, main)
    findings = []
    findings.append(dict(category="format", value=main["format"] if main else "none", confidence=100 if main and main["format"] != "unknown" else 0,
                         evidence=main["path"] if main else ""))
    if main and main.get("arch"):
        findings.append(dict(category="architecture", value=f"{main['arch']} ({main.get('bits', '?')}-bit, {main.get('endian')})",
                             confidence=100 if main["arch"] != "unknown" else 0, evidence="header"))
    for c in comp:
        findings.append(dict(category="compiler", value=c["name"] + (f" — {c['version']}" if c.get("version") else ""), confidence=c["confidence"],
                             evidence=c["evidence"]))
    for k, v in dbg.items():
        findings.append(dict(category="debug-info", value=f"{k}: {v}", confidence=100, evidence="header"))
    for m in mids:
        findings.append(dict(category="middleware", value=m["name"], confidence=m["confidence"], evidence=m["evidence"]))
    findings.append(dict(category="engine", value=elabel, confidence=min(escore, 100), evidence="; ".join(map(str, eev[:3]))))
    for p in prots:
        findings.append(dict(category="protection", value=f"{p['name']} ({p['kind']})", confidence=p["confidence"], evidence=p["evidence"]))

    def public(b: dict) -> dict:
        return {k: v for k, v in b.items() if not k.startswith("_")}

    return dict(
        target=str(root), kind=kind, main_binary=main["path"] if main else None,
        binaries=[public(b) for b in binaries],
        family=dict(key=family, label=FAMILIES[family][0], deliverable=FAMILIES[family][2]),
        engine=dict(key=ekey, label=elabel, confidence=min(escore, 100), evidence=eev[:4], **edet),
        other_engine_signals=[dict(key=k, label=ENGINES[k][0], confidence=min(s, 100), evidence=e[:2]) for k, (s, e, _) in ranked[1:5]],
        compiler=comp, debug=dbg, middleware=mids, protections=prots, findings=findings,
        routes=routes, playbook=routes[0]["playbook"] if routes else f"{SKILL}/references/engines/native-pc.md",
        warnings=warnings, stop=stop,
        files_indexed=len(ix.files) if ix else 1, index_truncated=bool(ix and ix.truncated),
    )


def format_report(r: dict) -> str:
    m = next((b for b in r["binaries"] if b["path"] == r["main_binary"]), None)
    L = [f"{r['target']}  ({r['kind']})"]
    if m:
        L.append(f"  binary:     {m['path']}  ({m.get('size', 0):,} bytes)")
        L.append(f"  format:     {m['format']}")
        L.append(f"  arch:       {m.get('arch')}  {m.get('bits')}-bit {m.get('endian')}" + (f"  platform={m['platform']}" if m.get("platform") else ""))
        extra = {k: m[k] for k in ("title", "title_id", "game_code", "game_id", "subsystem", "clr_version", "godot_version", "entry")
                 if m.get(k)}
        if extra:
            L.append("              " + ", ".join(f"{k}={v}" for k, v in extra.items()))
    for c in r["compiler"]:
        L.append(f"  compiler:   {c['name']}{' — ' + c['version'] if c.get('version') else ''}  [{c['confidence']}%] ({c['evidence']})")
    for k, v in r["debug"].items():
        L.append(f"  debug:      {k}: {v}")
    if not r["debug"]:
        L.append("  debug:      none found (stripped)")
    if m and m.get("imports"):
        L.append(f"  imports:    {', '.join(m['imports'][:12])}{' ...' if len(m['imports']) > 12 else ''}")
    for x in r["middleware"]:
        L.append(f"  middleware: {x['name']}  [{x['confidence']}%] ({x['evidence']}) -> replace with {x['replacement']}")
    e = r["engine"]
    L.append(f"  engine:     {e['label']}  [{e['confidence']}%]  evidence: {', '.join(map(str, e['evidence']))}")
    L.append(f"  family:     {r['family']['label']} -> deliverable: {r['family']['deliverable']}")
    if r["other_engine_signals"]:
        L.append("  also:       " + "; ".join(f"{o['label']} [{o['confidence']}%]" for o in r["other_engine_signals"]))
    if r["protections"]:
        for p in r["protections"]:
            L.append(f"  PROTECTION: {p['name']} ({p['kind']})  [{p['confidence']}%] {p['evidence']}")
    else:
        L.append("  protection: none found")
    L.append("  routes:")
    for i, rt in enumerate(r["routes"], 1):
        L.append(f"    {i}. {rt['method']}: {rt['description']}")
        L.append(f"       why: {rt['why']}")
        if rt.get("tools"):
            L.append(f"       tools: {', '.join(rt['tools'])}   (check: ud tools check --route {rt['tools_route']})")
    L.append(f"  playbook:   {r['playbook']}")
    for w in r["warnings"]:
        L.append(f"  WARNING:    {w}")
    if r["stop"]:
        L.append(f"  STOP:       {r['stop']['tell_the_user']}")
    return "\n".join(L)


def main(a):
    r = scan(a.path, context=not a.no_context)
    if a.json:
        emit_json(r)
    else:
        print(format_report(r))
    return PROBLEM if r["stop"] else OK


def register(sub):
    import argparse
    p = sub.add_parser("scan", help="identify a binary or install folder; ranked routes, playbook, tools",
                       description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("path", help="a binary (data/game.exe) or an install folder (data/)")
    p.add_argument("--no-context", action="store_true", help="don't look at the file's folder for engine layouts")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=main)
