"""Shared helpers: synthetic binary fixtures (built in-test, no real software involved) and repo helpers."""
from __future__ import annotations

import os
import shutil
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# --------------------------------------------------------------------------- binary builders

def pe(machine: int = 0x14C, sections=(".text", ".rdata", ".data"), imports=(), clr: bool = False, plus: bool = False,
       rich=None, subsystem: int = 2, overlay: bytes = b"", pdb: str | None = None) -> bytes:
    """A minimal but well-formed PE: DOS header, optional Rich header, PE header, sections, import table,
    optional CLR header + metadata root, optional CodeView debug entry."""
    e_lfanew = 0x100
    buf = bytearray(0x400 + 0x400 * len(sections))
    buf[0:2] = b"MZ"
    struct.pack_into("<I", buf, 0x3C, e_lfanew)
    if rich:
        key = 0x1A2B3C4D
        o = 0x80
        struct.pack_into("<4I", buf, o, 0x536E6144 ^ key, key, key, key)
        o += 16
        for prodid, build, count in rich:
            struct.pack_into("<II", buf, o, ((prodid << 16) | build) ^ key, count ^ key)
            o += 8
        buf[o:o + 4] = b"Rich"
        struct.pack_into("<I", buf, o + 4, key)
    buf[e_lfanew:e_lfanew + 4] = b"PE\0\0"
    optsz = 0xF0 if plus else 0xE0
    struct.pack_into("<HHIIIHH", buf, e_lfanew + 4, machine, len(sections), 0x60000000, 0, 0, optsz, 0x0102)
    opt = e_lfanew + 24
    struct.pack_into("<H", buf, opt, 0x20B if plus else 0x10B)
    if plus:
        struct.pack_into("<Q", buf, opt + 24, 0x140000000)
        struct.pack_into("<H", buf, opt + 68, subsystem)
        struct.pack_into("<I", buf, opt + 108, 16)
        dirs = opt + 112
    else:
        struct.pack_into("<I", buf, opt + 28, 0x400000)
        struct.pack_into("<H", buf, opt + 68, subsystem)
        struct.pack_into("<I", buf, opt + 92, 16)
        dirs = opt + 96
    sec = opt + optsz
    for i, name in enumerate(sections):
        va, raw = 0x1000 * (i + 1), 0x400 + 0x400 * i
        struct.pack_into("<8sIIIIIIHHI", buf, sec + 40 * i, name.encode()[:8], 0x400, va, 0x400, raw, 0, 0, 0, 0,
                         0x60000020 if i == 0 else 0x40000040)
    # import directory, CLR header and debug directory live in the first section (va 0x1000, raw 0x400)
    t = 0x400
    if imports:
        names_off = 0x200
        for i, dll in enumerate(imports):
            nva = 0x1000 + names_off
            struct.pack_into("<5I", buf, t + 20 * i, 0, 0, 0, nva, 0)
            buf[0x400 + names_off:0x400 + names_off + len(dll) + 1] = dll.encode() + b"\0"
            names_off += len(dll) + 1
        struct.pack_into("<II", buf, dirs + 8 * 1, 0x1000, 20 * (len(imports) + 1))
    if clr:
        struct.pack_into("<IHHIII", buf, t + 0x100, 72, 2, 5, 0x1180, 0x40, 1)
        struct.pack_into("<II", buf, dirs + 8 * 14, 0x1100, 72)
        md = 0x400 + 0x180
        buf[md:md + 4] = b"BSJB"
        struct.pack_into("<HHII", buf, md + 4, 1, 1, 0, 12)
        buf[md + 16:md + 28] = b"v4.0.30319\0\0"
    if pdb:
        dbg = 0x400 + 0x300
        struct.pack_into("<IIHHIIII", buf, dbg, 0, 0, 0, 0, 2, 24 + len(pdb) + 1, 0, 0x400 + 0x340)
        cv = 0x400 + 0x340
        buf[cv:cv + 4] = b"RSDS"
        buf[cv + 24:cv + 24 + len(pdb) + 1] = pdb.encode() + b"\0"
        struct.pack_into("<II", buf, dirs + 8 * 6, 0x1300, 28)
    return bytes(buf) + overlay


def elf(bits: int = 64, little: bool = True, machine: int = 62, osabi: int = 0, flags: int = 0, etype: int = 2,
        sections: dict | None = None) -> bytes:
    """ELF with real section headers (+ .shstrtab) so the parser sees section names."""
    e = "<" if little else ">"
    sections = dict(sections or {".text": b"\x90" * 16})
    names = [""] + list(sections) + [".shstrtab"]
    shstr = b"\0" + b"".join(n.encode() + b"\0" for n in names[1:])
    ehsize = 64 if bits == 64 else 52
    shentsize = 64 if bits == 64 else 40
    body = bytearray()
    offsets = []
    datas = list(sections.values()) + [shstr]
    for d in datas:
        offsets.append(ehsize + len(body))
        body += d
    shoff = ehsize + len(body)
    head = bytearray(ehsize)
    head[0:4] = b"\x7fELF"
    head[4], head[5], head[6], head[7] = (2 if bits == 64 else 1), (1 if little else 2), 1, osabi
    if bits == 64:
        struct.pack_into(e + "HHIQQQIHHHHHH", head, 16, etype, machine, 1, 0x401000, 0, shoff, flags, ehsize, 0, 0,
                         shentsize, len(names), len(names) - 1)
    else:
        struct.pack_into(e + "HHIIIIIHHHHHH", head, 16, etype, machine, 1, 0x401000, 0, shoff, flags, ehsize, 0, 0,
                         shentsize, len(names), len(names) - 1)
    sh = bytearray(shentsize)  # null section
    pos = 1
    for i, d in enumerate(datas):
        name_off = shstr.index(names[i + 1].encode() + b"\0") if names[i + 1] else 0
        typ = 3 if names[i + 1] == ".shstrtab" else 1
        ent = bytearray(shentsize)
        if bits == 64:
            struct.pack_into(e + "IIQQQQIIQQ", ent, 0, name_off, typ, 0, 0, offsets[i], len(d), 0, 0, 1, 0)
        else:
            struct.pack_into(e + "IIIIIIIIII", ent, 0, name_off, typ, 0, 0, offsets[i], len(d), 0, 0, 1, 0)
        sh += ent
        pos += 1
    return bytes(head) + bytes(body) + bytes(sh)


def xbe(title: str = "Test Game", title_id: int = 0x4D530004) -> bytes:
    base = 0x10000
    b = bytearray(0x1000)
    b[0:4] = b"XBEH"
    struct.pack_into("<I", b, 0x104, base)
    struct.pack_into("<I", b, 0x118, base + 0x200)
    struct.pack_into("<I", b, 0x154, base + 0x400)
    struct.pack_into("<II", b, 0x164, 1, base + 0x300)
    struct.pack_into("<I", b, 0x200 + 8, title_id)
    t = title.encode("utf-16-le")
    b[0x20C:0x20C + len(t)] = t
    b[0x300:0x308] = b"XAPILIB\0"
    struct.pack_into("<HHHH", b, 0x308, 1, 0, 5849, 0)
    b[0x400:0x409] = b"game.exe\0"
    return bytes(b)


def xex(encrypted: bool) -> bytes:
    b = bytearray(0x200)
    b[0:4] = b"XEX2"
    struct.pack_into(">I", b, 0x14, 2)
    struct.pack_into(">II", b, 0x18, 0x00040006, 0x100)
    struct.pack_into(">II", b, 0x20, 0x000003FF, 0x140)
    struct.pack_into(">I", b, 0x100 + 0x0C, 0x4D5307D1)
    struct.pack_into(">IHH", b, 0x140, 8, 1 if encrypted else 0, 1)
    return bytes(b)


def dol() -> bytes:
    b = bytearray(0x300)
    struct.pack_into(">I", b, 0x00, 0x100)            # text0 offset
    struct.pack_into(">I", b, 0x48, 0x80003100)       # text0 address
    struct.pack_into(">I", b, 0x90, 0x100)            # text0 size
    struct.pack_into(">I", b, 0xE0, 0x80003100)       # entry
    return bytes(b)


GBA_LOGO = bytes.fromhex("24ffae51699aa2213d84820a84e409ad")


def n64(swap: bool = False) -> bytes:
    h = bytearray(0x1000)
    h[0:4] = b"\x80\x37\x12\x40"
    h[0x20:0x34] = b"UD TEST ROM         "
    h[0x3B:0x3F] = b"NUDE"
    if swap:
        h[0::2], h[1::2] = h[1::2], h[0::2]
    return bytes(h)


def gba() -> bytes:
    b = bytearray(0x200)
    b[4:20] = GBA_LOGO
    b[0xA0:0xAC] = b"UDTESTGAME\0\0"
    b[0xAC:0xB0] = b"BUDE"
    b[0xB2] = 0x96
    b[0xBD] = (-(sum(b[0xA0:0xBD]) + 0x19)) & 0xFF
    return bytes(b)


def nds() -> bytes:
    b = bytearray(0x400)
    b[0:12] = b"UDTESTDS\0\0\0\0"
    b[0x0C:0x10] = b"AUDE"
    b[0xC0:0xD0] = GBA_LOGO
    struct.pack_into("<H", b, 0x15C, 0xCF56)
    return bytes(b)


def iso9660(system: str, extra: bytes) -> bytes:
    b = bytearray(0x10000)
    b[0x8000] = 1
    b[0x8001:0x8006] = b"CD001"
    b[0x8008:0x8008 + len(system)] = system.encode()
    b[0x9000:0x9000 + len(extra)] = extra
    return bytes(b)


def make(root: Path, files: dict) -> Path:
    for rel, data in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data if isinstance(data, bytes) else data.encode())
    return root


def zip_bytes(entries: dict) -> bytes:
    import io
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return bio.getvalue()


# --------------------------------------------------------------------------- repos

def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@localhost", "-c", "init.defaultBranch=main", *args],
                          cwd=cwd, capture_output=True, text=True, check=check)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """An empty git repo as the cwd (a fresh decomp repo)."""
    d = tmp_path / "decomp"
    d.mkdir()
    git(d, "init", "-q")
    monkeypatch.chdir(d)
    monkeypatch.setenv("UD_PUBLISH_OFFLINE", "1")
    return d


def ud(*args: str, cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run the CLI as a subprocess (python -m ud) so exit codes and stdout are real."""
    e = {**os.environ, "PYTHONPATH": str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""), **(env or {})}
    return subprocess.run([sys.executable, "-m", "ud", *args], cwd=cwd, capture_output=True, text=True, env=e,
                          encoding="utf-8", errors="replace")


def have_cxx() -> bool:
    return bool(shutil.which("cmake")) and bool(shutil.which("cl") or shutil.which("c++") or shutil.which("g++")
                                                or shutil.which("clang++") or os.name == "nt")
