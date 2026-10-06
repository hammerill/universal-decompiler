"""ud scan on synthetic fixtures: formats, compilers, debug info, middleware, engines, protections, routes."""
from __future__ import annotations

import json
import struct

import pytest
from conftest import (dol, elf, gba, iso9660, make, n64, nds, pe, ud, xbe, xex, zip_bytes)

from ud import formats, scan
from ud.formats import PYI_COOKIE

SEEN_FAMILIES: set[str] = set()


def run(path, context=True):
    r = scan.scan(str(path), context=context)
    SEEN_FAMILIES.add(r["family"]["key"])
    return r


def one(tmp_path, name, data, context=False):
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return run(p, context=context)


# --------------------------------------------------------------------------- native formats


def test_pe32_native_rich_imports_pdb(tmp_path):
    data = pe(rich=[(0x0104, 33145, 12), (0x0093, 30729, 90), (0x0001, 0, 1000)],
              imports=["KERNEL32.dll", "d3d9.dll", "binkw32.dll", "dinput8.dll"], pdb=r"C:\dev\game\Release\game.pdb")
    r = one(tmp_path, "game.exe", data)
    m = r["binaries"][0]
    assert m["format"] == "PE32" and m["arch"] == "x86" and m["bits"] == 32
    assert r["compiler"][0]["version"].startswith("Visual Studio 2022")   # newest product id wins over old import libs
    assert r["debug"]["pdb_path"].endswith("game.pdb")
    names = {x["name"] for x in r["middleware"]}
    assert {"Direct3D 9", "Bink Video", "DirectInput"} <= names
    assert r["family"]["key"] == "native"
    assert [x["method"] for x in r["routes"]] == ["hybrid-dll", "clean-room"]
    assert "ghidra" in r["routes"][0]["tools"]
    assert r["stop"] is None
    assert any("32-bit original" in w for w in r["warnings"])


def test_msvc_versions():
    assert formats.msvc_from_rich([(0x104, 33145, 1), (0x93, 30729, 500)]).startswith("Visual Studio 2022")
    assert formats.msvc_from_rich([(0xDD, 40629, 3)]).startswith("Visual Studio 2013")
    assert formats.msvc_from_rich([(0x83, 30729, 3)]).startswith("Visual Studio 2008 SP1")
    assert formats.msvc_from_rich([(0xAB, 50727, 3)]).startswith("Visual Studio 2012")
    assert formats.msvc_from_rich([(0x6D, 50727, 3)]).startswith("Visual Studio 2005")
    assert formats.msvc_from_rich([(0x104, 29913, 3)]).startswith("Visual Studio 2019")


def test_pe32plus_dll_no_hybrid(tmp_path):
    data = bytearray(pe(machine=0x8664, plus=True, imports=["KERNEL32.dll"]))
    struct.pack_into("<H", data, 0x100 + 22, 0x2022)   # IMAGE_FILE_DLL
    r = one(tmp_path, "engine.dll", bytes(data))
    assert r["binaries"][0]["format"] == "PE32+" and r["binaries"][0]["dll"]
    assert [x["method"] for x in r["routes"]] == ["clean-room"]


def test_elf64_gcc_dwarf(tmp_path):
    data = elf(sections={".text": b"\x90" * 32, ".comment": b"GCC: (GNU) 13.2.0\0", ".debug_info": b"\0" * 8, ".symtab": b"\0" * 24})
    r = one(tmp_path, "game", data)
    m = r["binaries"][0]
    assert m["format"] == "ELF" and m["arch"] == "x86-64"
    assert r["compiler"][0]["name"] == "GCC" and "13.2.0" in r["compiler"][0]["version"]
    assert r["debug"]["dwarf"] and r["debug"]["symbol_table"] == "ELF .symtab"
    assert r["routes"][0]["method"] == "clean-room"


def test_elf_ps2_ps3_psp(tmp_path):
    assert one(tmp_path, "SLUS_123.45", elf(bits=32, machine=8, flags=0x20924001))["family"]["key"] == "ps2"
    assert one(tmp_path, "EBOOT.ELF", elf(bits=64, little=False, machine=21, osabi=0x66))["family"]["key"] == "ps3"
    assert one(tmp_path, "BOOT.BIN", elf(bits=32, machine=8, flags=0x10A23001, etype=0xFFA0))["family"]["key"] == "psp"


def test_macho_arm64(tmp_path):
    b = bytearray(0x200)
    struct.pack_into("<IiiIIIII", b, 0, 0xFEEDFACF, 0x0100000C, 0, 2, 1, 72, 0, 0)
    struct.pack_into("<II16s", b, 32, 0x19, 72, b"__TEXT")
    r = one(tmp_path, "Game", bytes(b))
    assert r["binaries"][0]["format"] == "Mach-O" and r["binaries"][0]["arch"] == "arm64"
    assert r["family"]["key"] == "native"


def test_unknown_falls_back_to_native(tmp_path):
    r = one(tmp_path, "mystery.bin", bytes(range(256)) * 64)
    assert r["family"]["key"] == "native" and r["binaries"][0]["format"] == "unknown"
    assert r["playbook"].endswith("native-pc.md")


# --------------------------------------------------------------------------- managed, frozen


def test_dotnet_assembly(tmp_path):
    r = one(tmp_path, "Tool.exe", pe(imports=["mscoree.dll"], clr=True))
    assert r["binaries"][0]["clr_version"] == "v4.0.30319"
    assert r["family"]["key"] == "dotnet" and r["routes"][0]["method"] == "managed-decompile"


def test_xna_folder(tmp_path):
    make(tmp_path, {"Game.exe": pe(imports=["mscoree.dll"], clr=True), "FNA.dll": b"MZ", "Content/player.xnb": b"XNBw"})
    r = run(tmp_path)
    assert r["engine"]["key"] == "xna-fna" and r["family"]["key"] == "dotnet"


def test_dotnet_obfuscator_stops(tmp_path):
    data = pe(imports=["mscoree.dll"], clr=True) + b"ConfusedByAttribute" + b"\0" * 64
    r = one(tmp_path, "Prot.exe", data)
    assert r["stop"] and "ConfuserEx" in r["stop"]["protections"]


def test_pyinstaller_cookie(tmp_path):
    cookie = struct.pack("!8sIIii64s", PYI_COOKIE, 1000, 10, 10, 312, b"python312.dll")
    r = one(tmp_path, "App.exe", pe(imports=["KERNEL32.dll"]) + b"\0" * 300 + cookie)
    assert r["engine"]["key"] == "pyinstaller" and r["family"]["key"] == "python-frozen"
    assert r["binaries"][0]["appended"][0]["python"] == "3.12"


def test_cx_freeze_and_py2exe_folders(tmp_path):
    make(tmp_path / "a", {"App.exe": pe(), "lib/library.zip": zip_bytes({"m.pyc": b"x"}), "python312.dll": b"MZ"})
    assert run(tmp_path / "a")["engine"]["key"] == "cx_freeze"
    make(tmp_path / "b", {"App.exe": pe(), "library.zip": zip_bytes({"m.pyc": b"x"}), "python27.dll": b"MZ"})
    assert run(tmp_path / "b")["family"]["key"] == "python-frozen"


def test_jar_lwjgl(tmp_path):
    jar = zip_bytes({"META-INF/MANIFEST.MF": "Main-Class: game.Main\n", "game/Main.class": b"\xca\xfe\xba\xbe\0\0\0\x34",
                     "org/lwjgl/opengl/GL11.class": b"\xca\xfe\xba\xbe\0\0\0\x34"})
    r = one(tmp_path, "game.jar", jar)
    assert r["family"]["key"] == "java" and r["binaries"][0]["libraries"] == ["lwjgl"]
    assert r["routes"][0]["method"] == "managed-decompile"


# --------------------------------------------------------------------------- vendor engines (folders)


def test_unity_mono(tmp_path):
    make(tmp_path, {"Game.exe": pe(imports=["UnityPlayer.dll"]), "UnityPlayer.dll": pe(),
                    "Game_Data/globalgamemanagers": b"\0" * 20 + b"2022.3.21f1\0" + b"\0" * 64,
                    "Game_Data/Managed/Assembly-CSharp.dll": pe(clr=True)})
    r = run(tmp_path)
    assert r["engine"]["key"] == "unity-mono" and r["engine"]["unity_version"] == "2022.3.21f1"
    assert r["binaries"][0]["path"].endswith("Game.exe")
    assert r["routes"][0]["method"] == "engine-project"
    assert any("not reconstructed" in w for w in r["warnings"])


def test_unity_il2cpp_and_encrypted_metadata(tmp_path):
    files = {"Game.exe": pe(imports=["UnityPlayer.dll"]), "UnityPlayer.dll": pe(), "GameAssembly.dll": pe(),
             "Game_Data/globalgamemanagers": b"2021.3.5f1",
             "Game_Data/il2cpp_data/Metadata/global-metadata.dat": b"\xaf\x1b\xb1\xfa" + b"\0" * 32}
    r = run(make(tmp_path / "ok", files))
    assert r["family"]["key"] == "unity-il2cpp" and r["stop"] is None
    files["Game_Data/il2cpp_data/Metadata/global-metadata.dat"] = b"\x12\x34\x56\x78" * 8
    r = run(make(tmp_path / "enc", files))
    assert r["stop"] and "IL2CPP metadata" in r["stop"]["protections"]


def test_unreal4_version(tmp_path):
    exe = pe(machine=0x8664, plus=True) + "++UE4+Release-4.27".encode("utf-16-le") + b"\0" * 64
    make(tmp_path, {"Proj/Binaries/Win64/Proj-Win64-Shipping.exe": exe, "Proj/Content/Paks/Proj-WindowsNoEditor.pak": b"x",
                    "Proj.exe": pe()})
    r = run(tmp_path)
    assert r["engine"]["key"] == "unreal" and r["family"]["key"] == "unreal"
    assert r["binaries"][0]["path"].endswith("Proj-Win64-Shipping.exe")


def test_unreal3_upk(tmp_path):
    make(tmp_path, {"Binaries/Win32/Game.exe": pe(), "Game/CookedPC/Startup.upk": b"\xc1\x83\x2a\x9e" + b"\0" * 32})
    assert run(tmp_path)["engine"]["key"] == "unreal-3"


def test_godot_pck(tmp_path):
    make(tmp_path, {"game.exe": pe(machine=0x8664, plus=True), "game.pck": b"GDPC" + struct.pack("<4I", 2, 4, 2, 1)})
    r = run(tmp_path)
    assert r["family"]["key"] == "godot"
    assert one(tmp_path, "solo.pck", b"GDPC" + struct.pack("<4I", 2, 4, 3, 0))["binaries"][0]["godot_version"] == "4.3.0"


def test_gamemaker(tmp_path):
    make(tmp_path, {"Game.exe": pe(), "data.win": b"FORM\0\0\0\0GEN8\0\0\0\0\0\x11" + b"\0" * 32})
    r = run(tmp_path)
    assert r["family"]["key"] == "gamemaker" and r["routes"][0]["method"] == "engine-project"


# --------------------------------------------------------------------------- script engines


@pytest.mark.parametrize("files,engine,family", [
    ({"Game.exe": pe(), "www/js/rpg_core.js": "//", "nw.dll": b"MZ"}, "rpgmaker-mvmz", "rpgmaker"),
    ({"Game.exe": pe(), "Game.rgss3a": b"RGSSAD\0\x03"}, "rpgmaker-rgss", "rpgmaker"),
    ({"RPG_RT.exe": pe(), "RPG_RT.ldb": b"\x0bLcfDataBase"}, "rpgmaker-2k", "rpgmaker"),
    ({"Game.exe": pe(), "renpy/__init__.py": "#", "game/archive.rpa": b"RPA-3.0 0000"}, "renpy", "renpy"),
    ({"game.exe": pe(), "love.dll": b"MZ", "game.love": zip_bytes({"main.lua": "print(1)"})}, "love2d", "love2d"),
    ({"App.exe": pe(), "resources/app.asar": struct.pack("<IIII", 4, 100, 96, 90) + b'{"files":{}}'}, "electron", "html5"),
    ({"Game.exe": pe(), "package.nw": zip_bytes({"package.json": "{}"}), "nw.dll": b"MZ"}, "nwjs", "html5"),
    ({"Game.exe": pe(), "META-INF/AIR/application.xml": "<application/>", "Game.swf": b"CWS\x0a"}, "air", "flash-air"),
    ({"movie.swf": b"FWS\x09" + b"\0" * 32, "readme.txt": "hi"}, "flash", "flash-air"),
])
def test_script_engine_folders(tmp_path, files, engine, family):
    r = run(make(tmp_path, files))
    assert r["engine"]["key"] == engine and r["family"]["key"] == family
    assert r["routes"][0]["method"] == "script-recovery"


def test_rpgmaker_2k_prior_art_warning(tmp_path):
    r = run(make(tmp_path, {"RPG_RT.exe": pe(), "RPG_RT.ldb": b"x"}))
    assert any("EasyRPG" in w for w in r["warnings"])


def test_loose_script_files(tmp_path):
    assert one(tmp_path, "script.rpyc", b"RENPY RPC2" + b"\0" * 16)["family"]["key"] == "renpy"
    assert one(tmp_path, "app.asar", struct.pack("<IIII", 4, 100, 96, 90) + b'{"files":{}}')["family"]["key"] == "html5"
    assert one(tmp_path, "game.love", zip_bytes({"main.lua": "x", "conf.lua": "y"}))["family"]["key"] == "love2d"


# --------------------------------------------------------------------------- native engines


def test_native_engines(tmp_path):
    assert run(make(tmp_path / "rw", {"gta.exe": pe(), "models/gta3.img": b"x", "models/generic.txd": b"x", "data/x.col": b"x"}))["engine"]["key"] == "renderware"
    assert run(make(tmp_path / "id", {"game.exe": pe(), "base/pak0.pk3": zip_bytes({"a": "b"})}))["engine"]["key"] == "idtech"
    assert run(make(tmp_path / "src", {"hl2.exe": pe(), "hl2/gameinfo.txt": "x", "bin/engine.dll": pe()}))["engine"]["key"] == "source"
    r = run(make(tmp_path / "gb", {"Game.exe": pe(), "meshes/a.nif": b"Gamebryo File Format"}))
    assert r["engine"]["key"] == "gamebryo" and r["family"]["key"] == "native"


def test_renderware_string_and_middleware(tmp_path):
    r = one(tmp_path, "rw.exe", pe(imports=["KERNEL32.dll"]) + b"RenderWare Graphics 3.6\0" + b"AkSoundEngine\0")
    names = {x["name"]: x for x in r["middleware"]}
    assert "librw" in names["RenderWare"]["replacement"] and "Wwise" in names


# --------------------------------------------------------------------------- consoles


def test_console_files(tmp_path):
    r = one(tmp_path, "default.xbe", xbe())
    assert r["family"]["key"] == "xbox" and r["binaries"][0]["title"] == "Test Game" and r["binaries"][0]["title_id"] == "4D530004"
    assert r["binaries"][0]["xdk_libraries"] == ["XAPILIB 1.0.5849"]
    r = one(tmp_path, "default.xex", xex(encrypted=False))
    assert r["family"]["key"] == "xbox360" and r["stop"] is None and r["binaries"][0]["title_id"] == "4D5307D1"
    assert {x["method"] for x in r["routes"]} == {"static-recomp", "clean-room"}
    assert one(tmp_path, "enc.xex", xex(encrypted=True))["stop"]
    assert one(tmp_path, "main.dol", dol())["family"]["key"] == "gamecube-wii"
    assert one(tmp_path, "main", b"NSO0" + b"\0" * 252)["family"]["key"] == "switch"
    r = one(tmp_path, "game.nsp", b"PFS0" + b"\0" * 252)
    assert r["family"]["key"] == "switch" and r["stop"]
    r = one(tmp_path, "EBOOT.BIN", b"SCE\0" + b"\0" * 252)
    assert r["family"]["key"] == "ps3" and r["stop"] and "encrypted SELF" in r["stop"]["protections"]
    r = one(tmp_path, "SCUS_942.00", b"PS-X EXE" + struct.pack("<II", 0, 0) + struct.pack("<I", 0x80010000) + b"\0" * 0x38
            + b"Sony Computer Entertainment Inc. for North America area\0" + b"\0" * 0x700)
    assert r["family"]["key"] == "ps1"
    r = one(tmp_path, "rom.z64", n64())
    assert r["family"]["key"] == "n64" and r["binaries"][0]["title"] == "UD TEST ROM"
    assert [x["method"] for x in r["routes"]][0] == "static-recomp"
    assert one(tmp_path, "rom.v64", n64(swap=True))["binaries"][0]["title"] == "UD TEST ROM"
    r = one(tmp_path, "rom.gba", gba())
    assert r["family"]["key"] == "gba" and r["binaries"][0]["header_checksum_ok"]
    assert one(tmp_path, "rom.nds", nds())["family"]["key"] == "nds"
    assert one(tmp_path, "boot.elf", elf(bits=32, machine=8, flags=0x10A23001, etype=0xFFA0))["family"]["key"] == "psp"


def test_disc_images(tmp_path):
    gc = bytearray(0x10000)
    gc[0:6] = b"GUDE01"
    struct.pack_into(">I", gc, 0x1C, 0xC2339F3D)
    r = one(tmp_path, "game.iso", bytes(gc))
    assert r["family"]["key"] == "gamecube-wii" and any("container" in w for w in r["warnings"])
    wii = bytearray(0x10000)
    struct.pack_into(">I", wii, 0x18, 0x5D1C9EA3)
    assert one(tmp_path, "wii.iso", bytes(wii))["stop"]
    r = one(tmp_path, "ps2.iso", iso9660("PLAYSTATION", b"BOOT2 = cdrom0:\\SLUS_123.45;1\r\nVER = 1.00\r\n"))
    assert r["family"]["key"] == "ps2" and r["binaries"][0]["boot_executable"] == "SLUS_123.45"
    assert one(tmp_path, "ps1.bin", iso9660("PLAYSTATION", b"BOOT = cdrom:\\SCUS_942.00;1\r\n"))["family"]["key"] == "ps1"
    assert one(tmp_path, "psp.iso", iso9660("PSP GAME", b"PSP_GAME/SYSDIR"))["family"]["key"] == "psp"
    x = bytearray(0x20000)
    x[0x10000:0x10014] = b"MICROSOFT*XBOX*MEDIA"
    assert one(tmp_path, "game.xiso", bytes(x))["family"]["key"] == "xbox"


def test_console_folder_layouts(tmp_path):
    assert run(make(tmp_path / "ps3", {"PS3_GAME/USRDIR/EBOOT.BIN": b"SCE\0" + b"\0" * 60, "PS3_GAME/PARAM.SFO": b"x"}))["family"]["key"] == "ps3"
    assert run(make(tmp_path / "x360", {"default.xex": xex(False), "media/a.bin": b"x" * 600}))["family"]["key"] == "xbox360"
    assert run(make(tmp_path / "xbox", {"default.xbe": xbe()}))["family"]["key"] == "xbox"
    assert run(make(tmp_path / "nx", {"exefs/main": b"NSO0" + b"\0" * 1000, "exefs/main.npdm": b"META" + b"\0" * 1000}))["family"]["key"] == "switch"
    assert run(make(tmp_path / "ps2", {"SYSTEM.CNF": "BOOT2 = cdrom0:\\SLUS_123.45;1\n", "SLUS_123.45": elf(bits=32, machine=8, flags=0x20924001)}))["family"]["key"] == "ps2"
    assert run(make(tmp_path / "gc", {"sys/main.dol": dol(), "files/a.arc": b"x"}))["family"]["key"] == "gamecube-wii"


# --------------------------------------------------------------------------- protections, containers


@pytest.mark.parametrize("section,name", [(".vmp0", "VMProtect"), ("UPX0", "UPX"), (".bind", "SteamStub"), (".themida", "Themida")])
def test_packers_and_drm_stop(tmp_path, section, name):
    r = one(tmp_path, "p.exe", pe(sections=(section, ".text", ".data"), imports=["KERNEL32.dll"]))
    assert r["stop"] and name in r["stop"]["protections"]
    assert "never bypasses" in r["stop"]["tell_the_user"]


def test_cli_exit_code_on_protection(tmp_path):
    p = tmp_path / "p.exe"
    p.write_bytes(pe(sections=(".vmp0", ".text"), imports=["KERNEL32.dll"]))
    r = ud("scan", str(p), "--json")
    assert r.returncode == 1 and json.loads(r.stdout)["stop"]["reason"] == "protected"


def test_anti_cheat_folder_stops(tmp_path):
    r = run(make(tmp_path, {"Game.exe": pe(), "EasyAntiCheat/EasyAntiCheat_Setup.exe": pe()}))
    assert r["stop"] and "EasyAntiCheat" in r["stop"]["protections"]


def test_installer_and_archive_warnings(tmp_path):
    r = one(tmp_path, "setup.exe", pe(imports=["KERNEL32.dll"], overlay=b"Inno Setup Setup Data (6.2.0)" + b"\0" * 8192))
    assert any("installer" in w for w in r["warnings"])
    r = one(tmp_path, "game.7z", b"7z\xbc\xaf\x27\x1c" + b"\0" * 64)
    assert r["binaries"][0]["archive"] and any("extract" in w for w in r["warnings"])


def test_missing_path_is_usage_error(tmp_path):
    assert ud("scan", str(tmp_path / "nope")).returncode == 2


def test_text_report_and_json(tmp_path):
    p = tmp_path / "game.exe"
    p.write_bytes(pe(imports=["KERNEL32.dll", "d3d9.dll"]))
    r = ud("scan", str(p), "--no-context")
    assert r.returncode == 0 and "routes:" in r.stdout and "playbook:" in r.stdout
    data = json.loads(ud("scan", str(p), "--json").stdout)
    assert {"format", "architecture", "engine"} <= {f["category"] for f in data["findings"]}
    assert all(0 <= f["confidence"] <= 100 for f in data["findings"])


# --------------------------------------------------------------------------- coverage of §5.2


def test_every_family_recognised():
    """Runs last in this module (pytest keeps file order): every family of the spec was produced by a fixture."""
    missing = set(scan.FAMILIES) - SEEN_FAMILIES
    assert not missing, f"families never recognised by a fixture: {sorted(missing)}"
