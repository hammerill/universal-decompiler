"""Binary format parsers used by `ud scan`. Read-only, bounded reads, never executes anything.

Each `sniff_*` takes the first bytes of a file (`head`, at least 64 KiB when the file is that big), the last
bytes (`tail`), the size and the path, and returns a dict describing the format, or None if it isn't that
format. `analyze(path)` runs them all and adds compiler/debug/middleware/protection signals.
"""
from __future__ import annotations

import io
import math
import re
import struct
import zipfile
from pathlib import Path

HEAD = 1 << 16
TAIL = 1 << 16
STRING_BUDGET = 96 << 20        # bytes of a binary we grep for compiler/middleware strings


def u16(b, o, e="<"):
    return struct.unpack_from(e + "H", b, o)[0]


def u32(b, o, e="<"):
    return struct.unpack_from(e + "I", b, o)[0]


def u64(b, o, e="<"):
    return struct.unpack_from(e + "Q", b, o)[0]


def cstr(b: bytes, o: int, n: int = 256) -> str:
    end = b.find(b"\0", o, o + n)
    return b[o:end if end >= 0 else o + n].decode("latin-1", errors="replace")


def entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = [0] * 256
    for x in data:
        counts[x] += 1
    n = len(data)
    return -sum(c / n * math.log2(c / n) for c in counts if c)


def read_at(f, off: int, n: int) -> bytes:
    f.seek(off)
    return f.read(n)


# --------------------------------------------------------------------------- PE / COFF

PE_MACHINES = {0x14C: ("x86", 32), 0x8664: ("x86-64", 64), 0xAA64: ("arm64", 64), 0x1C0: ("arm", 32), 0x1C4: ("armv7-thumb", 32),
               0x1F2: ("powerpc-be (Xbox 360 PE)", 32), 0x200: ("ia64", 64), 0x166: ("mips", 32)}
DEBUG_TYPES = {2: "codeview", 13: "pogo", 16: "repro", 20: "ex_dllcharacteristics"}

# Section names that give a packer or protector away. Value: (name, kind, confidence).
PE_SECTION_PROTECTORS = {
    "upx0": ("UPX", "packer", 95), "upx1": ("UPX", "packer", 95), "upx2": ("UPX", "packer", 90),
    ".vmp0": ("VMProtect", "protector", 95), ".vmp1": ("VMProtect", "protector", 95), ".vmp2": ("VMProtect", "protector", 95),
    ".themida": ("Themida", "protector", 95), ".winlice": ("WinLicense", "protector", 95),
    ".bind": ("SteamStub (Steam DRM wrapper)", "drm", 90),
    ".enigma1": ("Enigma Protector", "protector", 95), ".enigma2": ("Enigma Protector", "protector", 95),
    ".aspack": ("ASPack", "packer", 95), ".adata": ("ASPack", "packer", 60),
    ".mpress1": ("MPRESS", "packer", 95), ".mpress2": ("MPRESS", "packer", 95),
    ".petite": ("Petite", "packer", 95), ".nsp0": ("NsPack", "packer", 90), ".nsp1": ("NsPack", "packer", 90),
    ".pec": ("PECompact", "packer", 80), ".pec2": ("PECompact", "packer", 80), "pec2": ("PECompact", "packer", 80),
    ".yp": ("Y0da Protector", "protector", 80), ".y0da": ("Y0da Protector", "protector", 90),
    ".securom": ("SecuROM", "drm", 95), ".dsstext": ("SecuROM", "drm", 70),
    ".arxan": ("Arxan", "protector", 90), ".ccg": ("CD-Cops / SafeDisc-era protection", "drm", 60),
    "stxt774": ("SafeDisc", "drm", 90), "stxt371": ("SafeDisc", "drm", 90),
    ".laserlo": ("LaserLock", "drm", 90), ".sforce3": ("StarForce", "drm", 90),
    ".boom": ("The Boomerang protector", "protector", 70), ".mackt": ("ImpRec-rebuilt (previously packed)", "packer", 50),
}

# MSVC toolset by compiler build number (Rich header). 50727 is shared by VS2005 and VS2012: the product id decides.
# MSVC toolset by compiler build number (Rich header). Build numbers repeat across generations, so the product id
# picks the table first: >= 0xFD is toolset 14.x (VS2015 and later). 50727 is both VS2005 and VS2012.
MSVC_OLD = [   # exact builds first, then ranges
    (21022, 21022, "Visual Studio 2008 (9.0)"), (30729, 30729, "Visual Studio 2008 SP1 (9.0)"),
    (30319, 30319, "Visual Studio 2010 (10.0)"), (40219, 40219, "Visual Studio 2010 SP1 (10.0)"),
    (21005, 21005, "Visual Studio 2013 (12.0)"), (9466, 9466, "Visual Studio .NET 2002 (7.0)"),
    (3077, 3077, "Visual Studio .NET 2003 (7.1)"), (6030, 6030, "Visual Studio .NET 2003 SP1 (7.1)"),
    (8000, 8999, "Visual C++ 6.0"), (51025, 61030, "Visual Studio 2012 (11.0)"), (30501, 40664, "Visual Studio 2013 (12.0)"),
]
MSVC_14 = [
    (23026, 24247, "Visual Studio 2015 (14.0)"), (25017, 26732, "Visual Studio 2017 (14.1x)"),
    (27508, 29913, "Visual Studio 2019 (14.2x)"), (30133, 35699, "Visual Studio 2022 (14.3x/14.4x)"),
    (35700, 65535, "Visual Studio 2026 (14.5x) or newer"),
]


def msvc_from_rich(entries: list[tuple[int, int, int]]) -> str | None:
    """entries: (prodid, build, count). The newest tool (highest product id) is the toolset that built and linked the
    program; counts mislead, because old import libraries (e.g. VS2008's) are linked into modern builds too."""
    tools = [(p, b) for p, b, _ in entries if p > 1 and b]
    if not tools:
        return None
    prodid = max(p for p, _ in tools)
    build = max(b for p, b in tools if p == prodid)
    if build == 50727:
        return "Visual Studio 2012 (11.0)" if prodid >= 0xAA else "Visual Studio 2005 (8.0)"
    for lo, hi, label in MSVC_14 if prodid >= 0xFD else MSVC_OLD:
        if lo <= build <= hi:
            return f"{label} [build {build}]"
    return f"MSVC (build {build})"


def rich_header(head: bytes, e_lfanew: int) -> list[tuple[int, int, int]]:
    end = head.find(b"Rich", 0x80, min(e_lfanew, len(head)))
    if end < 0:
        return []
    key = u32(head, end + 4)
    start = None
    for o in range(end - 4, 0x7C, -4):
        if u32(head, o) ^ key == 0x536E6144:  # "DanS"
            start = o
            break
    if start is None:
        return []
    out = []
    for o in range(start + 16, end, 8):
        compid, count = u32(head, o) ^ key, u32(head, o + 4) ^ key
        out.append((compid >> 16, compid & 0xFFFF, count))
    return out


def sniff_pe(head: bytes, f, size: int) -> dict | None:
    if head[:2] != b"MZ" or len(head) < 0x40:
        return None
    e = u32(head, 0x3C)
    if e + 0x100 > len(head):
        hdr = read_at(f, 0, e + 0x400)
    else:
        hdr = head
    if hdr[e:e + 4] != b"PE\0\0":
        return {"format": "MZ (DOS executable)", "arch": "x86-16", "bits": 16, "endian": "little"}
    machine, nsec = u16(hdr, e + 4), u16(hdr, e + 6)
    timestamp = u32(hdr, e + 8)
    optsz, chars = u16(hdr, e + 20), u16(hdr, e + 22)
    opt = e + 24
    magic = u16(hdr, opt)
    pe32plus = magic == 0x20B
    arch, bits = PE_MACHINES.get(machine, (f"machine 0x{machine:x}", 64 if pe32plus else 32))
    if pe32plus:
        image_base, subsystem, nrva, dirs = u64(hdr, opt + 24), u16(hdr, opt + 68), u32(hdr, opt + 108), opt + 112
    else:
        image_base, subsystem, nrva, dirs = u32(hdr, opt + 28), u16(hdr, opt + 68), u32(hdr, opt + 92), opt + 96
    secoff = opt + optsz
    if secoff + nsec * 40 > len(hdr):
        hdr = read_at(f, 0, secoff + nsec * 40 + 16)
    sections = []
    for i in range(min(nsec, 96)):
        s = secoff + i * 40
        name = hdr[s:s + 8].rstrip(b"\0").decode("latin-1", errors="replace")
        vsize, va, rawsize, rawptr = struct.unpack_from("<IIII", hdr, s + 8)
        flags = u32(hdr, s + 36)
        sections.append(dict(name=name, va=va, vsize=vsize, raw=rawptr, rawsize=rawsize, exec=bool(flags & 0x20000000)))

    def rva2off(rva: int) -> int | None:
        for s in sections:
            if s["va"] <= rva < s["va"] + max(s["vsize"], s["rawsize"]):
                return rva - s["va"] + s["raw"]
        return rva if rva < 0x1000 else None

    def ddir(i):
        if i >= nrva:
            return 0, 0
        return struct.unpack_from("<II", hdr, dirs + i * 8)

    info: dict = dict(format="PE32+" if pe32plus else "PE32", arch=arch, bits=bits, endian="little",
                      subsystem={2: "windows-gui", 3: "console", 1: "native", 10: "efi", 14: "xbox"}.get(subsystem, str(subsystem)),
                      dll=bool(chars & 0x2000), image_base=hex(image_base), timestamp=timestamp,
                      sections=[s["name"] for s in sections])
    # imports
    imports: list[str] = []
    for d, step, name_at in ((1, 20, 12), (13, 32, 4)):
        rva, sz = ddir(d)
        off = rva2off(rva) if rva else None
        if off is None:
            continue
        blob = read_at(f, off, min(max(sz, 20 * 64), 1 << 16))
        for o in range(0, len(blob) - step + 1, step):
            nrv = u32(blob, o + name_at)
            if nrv == 0:
                break
            no = rva2off(nrv)
            if no is None:
                continue
            nm = cstr(read_at(f, no, 128), 0, 128)
            if nm and nm.lower() not in (x.lower() for x in imports):
                imports.append(nm)
            if len(imports) > 400:
                break
    info["imports"] = imports
    # CLR (.NET)
    crva, _ = ddir(14)
    if crva:
        info["managed"] = True
        co = rva2off(crva)
        if co is not None:
            clr = read_at(f, co, 72)
            if len(clr) >= 20:
                mrva, flags = u32(clr, 8), u32(clr, 16)
                info["clr_flags"] = {"il_only": bool(flags & 1), "32bit_required": bool(flags & 2), "32bit_preferred": bool(flags & 0x20000)}
                mo = rva2off(mrva)
                if mo is not None:
                    md = read_at(f, mo, 64)
                    if md[:4] == b"BSJB":
                        vlen = u32(md, 12)
                        info["clr_version"] = cstr(md, 16, min(vlen, 40))
    # debug directory (PDB path)
    drva, dsz = ddir(6)
    do = rva2off(drva) if drva else None
    if do is not None:
        blob = read_at(f, do, min(dsz or 28, 28 * 16))
        types = []
        for o in range(0, len(blob) - 27, 28):
            typ, dsize, draw = u32(blob, o + 12), u32(blob, o + 16), u32(blob, o + 24)
            types.append(DEBUG_TYPES.get(typ, str(typ)))
            if typ == 2 and draw:
                cv = read_at(f, draw, min(dsize, 600))
                if cv[:4] == b"RSDS":
                    info["pdb"] = cstr(cv, 24, 520)
                elif cv[:4] == b"NB10":
                    info["pdb"] = cstr(cv, 16, 520)
        info["debug_entries"] = types
    info["has_symbols_table"] = u32(hdr, e + 12) != 0  # COFF symbol table (MinGW builds keep one)
    rich = rich_header(hdr if len(hdr) >= e else head, e)
    if rich:
        info["rich"] = msvc_from_rich(rich)
    # protections from section layout
    prots = []
    for s in sections:
        k = s["name"].lower()
        if k in PE_SECTION_PROTECTORS:
            n, kind, conf = PE_SECTION_PROTECTORS[k]
            if not any(p["name"] == n for p in prots):
                prots.append(dict(name=n, kind=kind, confidence=conf, evidence=f"section {s['name']}"))
    big_exec = [s for s in sections if s["exec"] and s["rawsize"] > (1 << 20)]
    for s in big_exec[:3]:
        sample = read_at(f, s["raw"] + s["rawsize"] // 4, 1 << 18)
        h = entropy(sample)
        if h > 7.6:
            prots.append(dict(name="encrypted or packed code (high-entropy executable section)", kind="protector", confidence=60,
                              evidence=f"section {s['name'] or '(unnamed)'}: entropy {h:.2f}/8 over 256 KiB; "
                                       "typical of Denuvo, VMProtect, Arxan or a custom packer"))
            break
    if not imports and not info.get("managed") and len(sections) <= 3 and size > 65536:
        prots.append(dict(name="no import table (packed?)", kind="packer", confidence=50, evidence="the PE imports nothing"))
    info["_protections"] = prots
    # overlay: data after the last section (installers, appended archives)
    last = max((s["raw"] + s["rawsize"] for s in sections), default=0)
    if last and size > last + 4096:
        info["overlay_bytes"] = size - last
    return info


# --------------------------------------------------------------------------- ELF

ELF_MACHINES = {3: "x86", 62: "x86-64", 40: "arm", 183: "arm64", 8: "mips", 10: "mips-le", 20: "powerpc", 21: "powerpc64",
                243: "riscv", 2: "sparc", 43: "sparcv9", 18: "sparc32plus", 4: "m68k", 42: "superh", 50: "ia64"}


def sniff_elf(head: bytes, f, size: int) -> dict | None:
    if head[:4] != b"\x7fELF" or len(head) < 0x40:
        return None
    cls, data, osabi = head[4], head[5], head[7]
    e = "<" if data == 1 else ">"
    bits = 64 if cls == 2 else 32
    etype, machine = u16(head, 16, e), u16(head, 18, e)
    if bits == 64:
        shoff, flags, shentsize, shnum, shstrndx = u64(head, 0x28, e), u32(head, 0x30, e), u16(head, 0x3A, e), u16(head, 0x3C, e), u16(head, 0x3E, e)
    else:
        shoff, flags, shentsize, shnum, shstrndx = u32(head, 0x20, e), u32(head, 0x24, e), u16(head, 0x2E, e), u16(head, 0x30, e), u16(head, 0x32, e)
    arch = ELF_MACHINES.get(machine, f"machine {machine}")
    info: dict = dict(format="ELF", arch=arch, bits=bits, endian="little" if data == 1 else "big",
                      type={1: "relocatable", 2: "executable", 3: "shared object / PIE", 4: "core", 0xFFA0: "PSP PRX"}.get(etype, hex(etype)))
    platform = None
    if osabi == 0x66:
        platform = "ps3"
        info["os_abi"] = "CellOS Lv-2 (PlayStation 3)"
    elif machine == 8 and (flags & 0x00FF0000) == 0x00920000:
        platform = "ps2"
        info["cpu"] = "R5900 (Emotion Engine)"
    elif machine == 8 and ((flags & 0x00FF0000) == 0x00840000 or etype == 0xFFA0):
        platform = "psp"
        info["cpu"] = "Allegrex"
    elif osabi == 0xCA:
        platform = "wiiu"
    sections: list[str] = []
    needed: list[str] = []
    if shoff and shnum and shentsize >= (64 if bits == 64 else 40) and shoff + shnum * shentsize <= size and shnum < 4096:
        sh = read_at(f, shoff, shnum * shentsize)
        ents = []
        for i in range(shnum):
            o = i * shentsize
            if bits == 64:
                name, typ, off, sz, link = u32(sh, o, e), u32(sh, o + 4, e), u64(sh, o + 24, e), u64(sh, o + 32, e), u32(sh, o + 40, e)
            else:
                name, typ, off, sz, link = u32(sh, o, e), u32(sh, o + 4, e), u32(sh, o + 16, e), u32(sh, o + 20, e), u32(sh, o + 24, e)
            ents.append((name, typ, off, sz, link))
        if shstrndx < len(ents):
            _, _, so, ss, _ = ents[shstrndx]
            strtab = read_at(f, so, min(ss, 1 << 20))
            for name, typ, off, sz, link in ents:
                nm = cstr(strtab, name, 128) if name < len(strtab) else "?"
                sections.append(nm)
                if typ == 6 and link < len(ents):  # SHT_DYNAMIC -> DT_NEEDED
                    dyn = read_at(f, off, min(sz, 1 << 16))
                    _, _, dso, dss, _ = ents[link]
                    dstr = read_at(f, dso, min(dss, 1 << 20))
                    step = 16 if bits == 64 else 8
                    for o in range(0, len(dyn) - step + 1, step):
                        tag = u64(dyn, o, e) if bits == 64 else u32(dyn, o, e)
                        val = u64(dyn, o + 8, e) if bits == 64 else u32(dyn, o + 4, e)
                        if tag == 0:
                            break
                        if tag == 1 and val < len(dstr):
                            needed.append(cstr(dstr, val, 128))
                if nm == ".comment" and sz:
                    info["comment"] = [c.decode("latin-1", errors="replace") for c in read_at(f, off, min(sz, 4096)).split(b"\0") if c][:6]
    info["sections"] = sections[:80]
    info["needed"] = needed
    info["dwarf"] = any(s.startswith((".debug_info", ".zdebug_info")) for s in sections)
    info["symtab"] = ".symtab" in sections
    if any(s.startswith(".sce") or s == ".rodata.sceModuleInfo" for s in sections):
        platform = platform or ("psp" if machine == 8 else "ps3" if machine in (20, 21) else None)
    if machine in (20, 21) and platform is None and data == 2 and ".sceStub.text" in sections:
        platform = "ps3"
    if platform:
        info["platform"] = platform
    return info


# --------------------------------------------------------------------------- Mach-O

MACHO_CPUS = {7: "x86", 0x01000007: "x86-64", 12: "arm", 0x0100000C: "arm64", 18: "powerpc", 0x01000012: "powerpc64"}


def sniff_macho(head: bytes, f, size: int) -> dict | None:
    m = head[:4]
    if m == b"\xca\xfe\xba\xbe" and len(head) >= 8 and 0 < u32(head, 4, ">") < 20:
        n = u32(head, 4, ">")
        archs = [MACHO_CPUS.get(u32(head, 8 + i * 20, ">"), "?") for i in range(n)]
        return dict(format="Mach-O universal (fat)", arch="+".join(archs), bits=64 if any("64" in a for a in archs) else 32, endian="big")
    if m not in (b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe"):
        return None
    e = ">" if m[:2] == b"\xfe\xed" else "<"
    is64 = m in (b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe")
    cpu, ftype, ncmds = u32(head, 4, e), u32(head, 12, e), u32(head, 16, e)
    info: dict = dict(format="Mach-O", arch=MACHO_CPUS.get(cpu, f"cpu {cpu:#x}"), bits=64 if is64 else 32,
                      endian="big" if e == ">" else "little",
                      type={1: "object", 2: "executable", 6: "dylib", 8: "bundle"}.get(ftype, str(ftype)))
    o = 32 if is64 else 28
    dylibs, segs, prots = [], [], []
    for _ in range(min(ncmds, 512)):
        if o + 8 > len(head):
            break
        cmd, csz = u32(head, o, e), u32(head, o + 4, e)
        if cmd in (0xC, 0x18 | 0x80000000, 0x1F | 0x80000000):  # LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB, LC_REEXPORT_DYLIB
            dylibs.append(cstr(head, o + u32(head, o + 8, e), 256))
        elif cmd in (0x1, 0x19):  # LC_SEGMENT(_64)
            segs.append(cstr(head, o + 8, 16))
        elif cmd == 0x2:  # LC_SYMTAB
            info["nsyms"] = u32(head, o + 12, e)
        elif cmd in (0x21, 0x2C) and u32(head, o + 16, e) != 0:  # LC_ENCRYPTION_INFO(_64) with cryptid
            prots.append(dict(name="FairPlay encryption (cryptid set)", kind="encryption", confidence=95, evidence="LC_ENCRYPTION_INFO"))
        if csz < 8:
            break
        o += csz
    info.update(dylibs=dylibs, segments=segs, dwarf="__DWARF" in segs, _protections=prots)
    return info


# --------------------------------------------------------------------------- consoles

def sniff_xbe(head: bytes, f, size: int) -> dict | None:
    if head[:4] != b"XBEH" or len(head) < 0x180:
        return None
    base = u32(head, 0x104)
    info: dict = dict(format="XBE (original Xbox executable)", arch="x86", bits=32, endian="little", platform="xbox", base=hex(base))
    try:
        cert = u32(head, 0x118) - base
        if 0 < cert < len(head) - 0x60:
            info["title_id"] = f"{u32(head, cert + 8):08X}"
            info["title"] = head[cert + 0x0C:cert + 0x0C + 80].decode("utf-16-le", errors="replace").split("\0")[0]
        nlib, libaddr = u32(head, 0x164), u32(head, 0x168) - base
        libs = []
        for i in range(min(nlib, 64)):
            o = libaddr + i * 16
            if o + 16 > len(head):
                break
            name = head[o:o + 8].rstrip(b"\0").decode("latin-1", errors="replace")
            major, minor, build = struct.unpack_from("<HHH", head, o + 8)
            libs.append(f"{name} {major}.{minor}.{build}")
        info["xdk_libraries"] = libs
        dbg = u32(head, 0x154) - base
        if 0 < dbg < len(head):
            info["debug_filename"] = cstr(head, dbg, 260)
    except struct.error:
        pass
    return info


def sniff_xex(head: bytes, f, size: int) -> dict | None:
    if head[:3] != b"XEX" or len(head) < 0x18:
        return None
    info: dict = dict(format=f"XEX ({head[:4].decode('latin-1')}, Xbox 360 executable)", arch="powerpc (Xenon)", bits=64, endian="big",
                      platform="xbox360")
    prots = []
    try:
        count = u32(head, 0x14, ">")
        for i in range(min(count, 64)):
            key, val = u32(head, 0x18 + i * 8, ">"), u32(head, 0x1C + i * 8, ">")
            if key == 0x00040006 and val + 0x18 <= len(head):
                info["title_id"] = f"{u32(head, val + 0x0C, '>'):08X}"
            elif key == 0x000183FF and val + 4 <= len(head):
                info["original_pe_name"] = cstr(head, val + 4, 64)
            elif key == 0x000003FF and val + 8 <= len(head):
                enc, comp = u16(head, val + 4, ">"), u16(head, val + 6, ">")
                info["encrypted"] = enc != 0
                info["compression"] = {0: "none", 1: "basic", 2: "normal (LZX)", 3: "delta"}.get(comp, str(comp))
        if info.get("encrypted"):
            prots.append(dict(name="encrypted XEX", kind="encryption", confidence=95, evidence="file format info: encryption type != 0"))
    except struct.error:
        pass
    info["_protections"] = prots
    return info


def sniff_sce(head: bytes, f, size: int) -> dict | None:
    if head[:4] == b"SCE\0":
        return dict(format="SELF/SPRX (signed, encrypted PlayStation 3 executable)", arch="powerpc64 (Cell PPU)", bits=64, endian="big",
                    platform="ps3", _protections=[dict(name="encrypted SELF", kind="encryption", confidence=95, evidence="SCE header")])
    if head[:4] == b"\0PBP":
        return dict(format="EBOOT.PBP (PSP package)", arch="mips (Allegrex)", bits=32, endian="little", platform="psp")
    if head[:4] == b"~PSP":
        return dict(format="~PSP (encrypted PSP executable)", arch="mips (Allegrex)", bits=32, endian="little", platform="psp",
                    _protections=[dict(name="encrypted PSP executable", kind="encryption", confidence=95, evidence="~PSP header")])
    return None


def sniff_dol(head: bytes, f, size: int, path: Path) -> dict | None:
    if len(head) < 0x100:
        return None
    ext = path.suffix.lower()
    try:
        offs = struct.unpack_from(">18I", head, 0)
        addrs = struct.unpack_from(">18I", head, 0x48)
        sizes = struct.unpack_from(">18I", head, 0x90)
        entry = u32(head, 0xE0, ">")
    except struct.error:
        return None
    if ext == ".dol" or (0x80000000 <= entry < 0x81800000):
        ok = 0x80000000 <= entry < 0x81800000 and sizes[0] > 0
        for o, a, s in zip(offs, addrs, sizes, strict=True):
            if s == 0:
                continue
            if o < 0x100 or o + s > size or not (0x80000000 <= a < 0x81800000):
                ok = False
                break
        if ok:
            return dict(format="DOL (GameCube/Wii executable)", arch="powerpc (Gekko/Broadway)", bits=32, endian="big",
                        platform="gamecube-wii", entry=hex(entry))
    if ext == ".rel" and size > 0x40:
        version = u32(head, 0x1C, ">")
        nsec, secoff = u32(head, 0x0C, ">"), u32(head, 0x10, ">")
        if 1 <= version <= 3 and 0 < nsec < 256 and secoff < size:
            return dict(format="REL (GameCube/Wii relocatable module)", arch="powerpc (Gekko/Broadway)", bits=32, endian="big",
                        platform="gamecube-wii", module_id=u32(head, 0, ">"))
    return None


def sniff_switch(head: bytes, f, size: int, path: Path) -> dict | None:
    ext = path.suffix.lower()
    if head[:4] == b"NSO0":
        return dict(format="NSO (Switch executable)", arch="arm64", bits=64, endian="little", platform="switch")
    if len(head) >= 0x14 and head[0x10:0x14] == b"NRO0":
        return dict(format="NRO (Switch homebrew/relocatable executable)", arch="arm64", bits=64, endian="little", platform="switch")
    if head[:4] == b"META" and ext in (".npdm", ""):
        return dict(format="NPDM (Switch program metadata)", arch="arm64", bits=64, endian="little", platform="switch")
    enc = [dict(name="encrypted Switch content (NCA)", kind="encryption", confidence=90, evidence="")]
    if head[:4] == b"PFS0":
        enc[0]["evidence"] = "PFS0 container (NSP) holding NCAs"
        return dict(format="NSP (Switch package)", arch="arm64", bits=64, endian="little", platform="switch", _protections=enc)
    if len(head) >= 0x104 and head[0x100:0x104] == b"HEAD":
        enc[0]["evidence"] = "XCI cartridge image"
        return dict(format="XCI (Switch cartridge image)", arch="arm64", bits=64, endian="little", platform="switch", _protections=enc)
    if ext == ".nca":
        enc[0]["evidence"] = ".nca file"
        return dict(format="NCA (Switch content archive)", arch="arm64", bits=64, endian="little", platform="switch", _protections=enc)
    return None


GBA_LOGO_START = bytes.fromhex("24ffae51699aa2213d84820a84e409ad")   # first 16 bytes of the boot logo (GBA @0x04, NDS @0xC0)


def sniff_rom(head: bytes, f, size: int, path: Path) -> dict | None:
    m4 = head[:4]
    n64 = {b"\x80\x37\x12\x40": "z64 (big-endian)", b"\x37\x80\x40\x12": "v64 (byte-swapped)", b"\x40\x12\x37\x80": "n64 (little-endian)"}
    if m4 in n64 and len(head) >= 0x40:
        h = bytearray(head[:0x40])
        if m4 == b"\x37\x80\x40\x12":
            h[0::2], h[1::2] = h[1::2], h[0::2]
        elif m4 == b"\x40\x12\x37\x80":
            for i in range(0, 0x40, 4):
                h[i:i + 4] = h[i:i + 4][::-1]
        return dict(format=f"Nintendo 64 ROM, {n64[m4]}", arch="mips (VR4300)", bits=64, endian="big", platform="n64",
                    title=bytes(h[0x20:0x34]).decode("ascii", errors="replace").strip(), game_code=bytes(h[0x3B:0x3F]).decode("ascii", errors="replace"))
    if len(head) >= 0xC0 and head[4:20] == GBA_LOGO_START and head[0xB2] == 0x96:
        chk = (-(sum(head[0xA0:0xBD]) + 0x19)) & 0xFF
        return dict(format="Game Boy Advance ROM", arch="arm (ARM7TDMI, ARMv4T)", bits=32, endian="little", platform="gba",
                    title=head[0xA0:0xAC].decode("ascii", errors="replace").strip("\0 "), game_code=head[0xAC:0xB0].decode("ascii", errors="replace"),
                    header_checksum_ok=chk == head[0xBD])
    if len(head) >= 0x160 and (u16(head, 0x15C) == 0xCF56 or head[0xC0:0xD0] == GBA_LOGO_START):
        return dict(format="Nintendo DS ROM", arch="arm (ARM946E-S + ARM7TDMI)", bits=32, endian="little", platform="nds",
                    title=head[0:12].decode("ascii", errors="replace").strip("\0 "), game_code=head[0x0C:0x10].decode("ascii", errors="replace"),
                    arm9_entry=hex(u32(head, 0x24)))
    if head[:8] == b"PS-X EXE":
        return dict(format="PS-X EXE (PlayStation executable)", arch="mips (R3000A)", bits=32, endian="little", platform="ps1",
                    entry=hex(u32(head, 0x10)), region=cstr(head, 0x4C, 64))
    # disc images
    if len(head) >= 0x20 and u32(head, 0x1C, ">") == 0xC2339F3D:
        return dict(format="GameCube disc image", arch="powerpc (Gekko)", bits=32, endian="big", platform="gamecube-wii",
                    game_id=head[:6].decode("ascii", errors="replace"), title=cstr(head, 0x20, 64), container=True)
    if len(head) >= 0x20 and u32(head, 0x18, ">") == 0x5D1C9EA3:
        return dict(format="Wii disc image", arch="powerpc (Broadway)", bits=32, endian="big", platform="gamecube-wii",
                    game_id=head[:6].decode("ascii", errors="replace"), title=cstr(head, 0x20, 64), container=True,
                    _protections=[dict(name="encrypted Wii disc partitions", kind="encryption", confidence=90, evidence="Wii disc magic")])
    if head[:4] in (b"RVZ\x01", b"WIA\x01") or (len(head) >= 4 and u32(head, 0) == 0xB10BC001):
        return dict(format="compressed GameCube/Wii image (RVZ/WIA/GCZ)", arch="powerpc", bits=32, endian="big", platform="gamecube-wii",
                    container=True)
    return None


def sniff_disc(f, size: int, path: Path) -> dict | None:
    """ISO9660 / XDVDFS images. Reads only a few fixed offsets plus the first 4 MiB."""
    xdvd = {0x10000: "Xbox (XISO) or an extracted Xbox 360 game partition", 0x18310000: "Xbox (XGD1 full image)",
            0xFDA0000: "Xbox 360 (XGD2)", 0x2090000: "Xbox 360 (XGD3)"}
    for off, label in xdvd.items():
        if off + 20 <= size and read_at(f, off, 20) == b"MICROSOFT*XBOX*MEDIA":
            plat = "xbox360" if "360 (" in label else "xbox"
            return dict(format=f"XDVDFS disc image: {label}", arch="x86" if plat == "xbox" else "powerpc (Xenon)", bits=32 if plat == "xbox" else 64,
                        endian="little" if plat == "xbox" else "big", platform=plat, container=True)
    for off in (0x8001, 0x9319):
        if off + 5 <= size and read_at(f, off, 5) == b"CD001":
            pvd = read_at(f, off - 1, 0x80)
            system = pvd[8:40].decode("ascii", errors="replace").strip()
            volume = pvd[40:72].decode("ascii", errors="replace").strip()
            early = read_at(f, 0, min(size, 4 << 20))
            info: dict = dict(format="ISO9660 disc image" + (" (raw 2352-byte sectors)" if off == 0x9319 else ""), system_id=system,
                        volume_id=volume, container=True)
            if b"BOOT2" in early or system.startswith("PLAYSTATION") and b"BOOT2" in early:
                info.update(platform="ps2", arch="mips (R5900)", bits=32, endian="little")
            elif b"BOOT =" in early or b"BOOT=" in early or system.startswith("PLAYSTATION"):
                info.update(platform="ps1", arch="mips (R3000A)", bits=32, endian="little")
            if system.startswith("PSP GAME") or b"PSP_GAME" in early:
                info.update(platform="psp", arch="mips (Allegrex)", bits=32, endian="little")
            if b"PS3_GAME" in early or b"PlayStation3" in early[:0x1000]:
                info.update(platform="ps3", arch="powerpc64 (Cell PPU)", bits=64, endian="big",
                            _protections=[dict(name="encrypted PS3 disc image", kind="encryption", confidence=80, evidence="PS3 disc markers")])
            m = re.search(rb"BOOT2?\s*=\s*cdrom0?:\\?([A-Z0-9_.]+)", early)
            if m:
                info["boot_executable"] = m.group(1).decode("ascii", errors="replace")
            return info
    return None


# --------------------------------------------------------------------------- managed, engines, archives

def sniff_misc(head: bytes, tail: bytes, f, size: int, path: Path) -> dict | None:
    if head[:4] == b"\xca\xfe\xba\xbe" and len(head) >= 8 and u16(head, 6, ">") >= 45:
        return dict(format=f"Java class file (class version {u16(head, 6, '>')})", arch="jvm", bits=0, endian="big", family_hint="java")
    if head[:3] in (b"FWS", b"CWS", b"ZWS"):
        return dict(format=f"SWF (Flash movie, version {head[3]})", arch="avm", bits=0, endian="little", family_hint="flash-air")
    if head[:4] == b"FORM" and head[8:12] == b"GEN8":
        return dict(format="GameMaker data file (data.win)", arch="gml", bits=0, endian="little", family_hint="gamemaker",
                    bytecode_version=head[17] if len(head) > 17 else None)
    if head[:4] == b"GDPC":
        maj, mi, pa = struct.unpack_from("<3I", head, 8)
        return dict(format=f"Godot PCK (engine {maj}.{mi}.{pa})", arch="godot", bits=0, endian="little", family_hint="godot",
                    godot_version=f"{maj}.{mi}.{pa}")
    if head[:7] == b"RPA-3.0" or head[:7] == b"RPA-2.0" or head[:7] == b"RPA-3.2":
        return dict(format="Ren'Py archive (RPA)", arch="python", bits=0, endian="little", family_hint="renpy")
    if head[:10] == b"RENPY RPC2":
        return dict(format="Ren'Py compiled script (.rpyc)", arch="python", bits=0, endian="little", family_hint="renpy")
    if head[:7] == b"RGSSAD\0":
        return dict(format=f"RPG Maker RGSS archive (v{head[7]})", arch="ruby", bits=0, endian="little", family_hint="rpgmaker")
    if head[:7] in (b"UnityFS", b"UnityWe", b"UnityRa"):
        return dict(format="Unity asset bundle", arch="unity", bits=0, endian="big", family_hint="unity-mono")
    if head[:4] == b"\xc1\x83\x2a\x9e":
        return dict(format="Unreal package (.uasset/.upk)", arch="unreal", bits=0, endian="little", family_hint="unreal")
    if b"\xe1\x12\x6f\x5a" in tail[-300:]:
        return dict(format="Unreal pak archive", arch="unreal", bits=0, endian="little", family_hint="unreal")
    if len(head) >= 24 and u32(head, 0) == 4 and head[16:25] == b'{"files":':
        return dict(format="Electron asar archive", arch="javascript", bits=0, endian="little", family_hint="html5")
    if head[:4] == b"\xaf\x1b\xb1\xfa":
        return dict(format="IL2CPP global-metadata.dat", arch="il2cpp", bits=0, endian="little", family_hint="unity-il2cpp",
                    metadata_version=u32(head, 4))
    if head[:6] == b"7z\xbc\xaf\x27\x1c":
        return dict(format="7-Zip archive", arch="archive", bits=0, endian="little", archive=True)
    if head[:6] == b"Rar!\x1a\x07":
        return dict(format="RAR archive", arch="archive", bits=0, endian="little", archive=True)
    if head[:4] == b"MSCF":
        return dict(format="Microsoft Cabinet", arch="archive", bits=0, endian="little", archive=True)
    if head[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return dict(format="OLE compound file (MSI installer?)", arch="archive", bits=0, endian="little", archive=True, installer=True)
    for magic, name in ((b"\x1f\x8b", "gzip"), (b"\xfd7zXZ\0", "xz"), (b"\x28\xb5\x2f\xfd", "zstd"), (b"BZh", "bzip2")):
        if head.startswith(magic):
            return dict(format=f"{name} stream", arch="archive", bits=0, endian="little", archive=True)
    if len(head) > 262 and head[257:262] == b"ustar":
        return dict(format="tar archive", arch="archive", bits=0, endian="little", archive=True)
    if head[:4] == b"PK\x03\x04":
        return sniff_zip(f, path)
    return None


def zip_names(f, limit: int = 20000) -> list[str] | None:
    try:
        f.seek(0)
        with zipfile.ZipFile(f) as z:
            return [n for n in z.namelist()[:limit]]
    except (zipfile.BadZipFile, OSError, ValueError, RuntimeError):
        return None


def sniff_zip(f, path: Path) -> dict:
    names = zip_names(f) or []
    low = [n.lower() for n in names]
    base = dict(arch="archive", bits=0, endian="little", entries=len(names))
    if any(n == "meta-inf/air/application.xml" for n in low):
        return dict(base, format="Adobe AIR package (.air)", arch="avm", family_hint="flash-air")
    if "main.lua" in low or "conf.lua" in low:
        return dict(base, format="LÖVE game archive (.love)", arch="lua", family_hint="love2d")
    if any(n.endswith(".class") for n in low) or "meta-inf/manifest.mf" in low:
        jvm: dict = dict(base, format="Java archive (JAR)", arch="jvm", family_hint="java")
        jvm["libraries"] = sorted({lib for lib in ("lwjgl", "libgdx", "slick", "jogl", "jmonkeyengine") if any(lib in n for n in low)})
        return jvm
    if any(n.endswith(".pyc") for n in low):
        return dict(base, format="ZIP of Python bytecode (library.zip / base_library.zip)", arch="python", family_hint="python-frozen")
    return dict(base, format="ZIP archive", archive=True)


PYI_COOKIE = b"MEI\x0c\x0b\x0a\x0b\x0e"
DOTNET_BUNDLE_SIG = bytes([0x8b, 0x12, 0x02, 0xb9, 0x6a, 0x61, 0x20, 0x38, 0x72, 0x7b, 0x93, 0x02, 0x14, 0xd7, 0xa0, 0x32,
                           0x13, 0xf5, 0xb9, 0xe6, 0xef, 0xae, 0x33, 0x18, 0xee, 0x3b, 0x2d, 0xce, 0x24, 0xb3, 0x6a, 0xae])


def appended_payloads(head: bytes, tail: bytes, f, size: int) -> list[dict]:
    """Things glued to an executable: PyInstaller archives, Godot PCKs, LÖVE zips, .NET single-file bundles, installers."""
    out = []
    i = tail.rfind(PYI_COOKIE)
    if i >= 0 and len(tail) - i >= 88:
        try:
            pyver = struct.unpack_from("!i", tail, i + 20)[0]
            lib = cstr(tail, i + 24, 64)
            ver = f"{pyver // 100}.{pyver % 100}" if pyver >= 300 else f"{pyver // 10}.{pyver % 10}"
        except struct.error:
            ver, lib = "?", ""
        out.append(dict(kind="pyinstaller", family_hint="python-frozen", python=ver, python_lib=lib))
    if tail[-4:] == b"GDPC":
        out.append(dict(kind="godot-pck (embedded)", family_hint="godot"))
    if b"PK\x05\x06" in tail[-1024:]:
        # a zip at the end of an exe: LÖVE fused game, py2exe/cx_Freeze library, or a self-extracting archive
        names = zip_names(f, 4000) or []
        low = [n.lower() for n in names]
        if "main.lua" in low:
            out.append(dict(kind="love-fused", family_hint="love2d"))
        elif any(n.endswith(".pyc") for n in low):
            out.append(dict(kind="python-zip (py2exe/cx_Freeze)", family_hint="python-frozen"))
        elif names:
            out.append(dict(kind="appended zip", entries=len(names)))
    return out


# --------------------------------------------------------------------------- strings: compiler, middleware, engines

COMPILER_STRINGS = [
    ("GCC", rb"GCC: \([^)\x00]{0,80}\) [0-9][0-9.]*"),
    ("Clang/LLVM", rb"clang version [0-9][0-9.]*"),
    ("MinGW-w64", rb"Mingw-w64 runtime failure|__mingw_|libgcc_s_(?:dw2|seh)"),
    ("Metrowerks CodeWarrior", rb"Metrowerks|CodeWarrior|MW_EABI"),
    ("SN Systems ProDG", rb"SN Systems|ProDG|SN TARGET|snc_"),
    ("Borland/Embarcadero (Delphi/C++Builder)", rb"Borland|Embarcadero|FastMM"),
    ("Watcom", rb"WATCOM C|Open Watcom"),
    ("Intel C++", rb"Intel\(R\) C\+\+|Intel\(R\) oneAPI"),
    ("Go", rb"Go build ID: |runtime\.gopanic"),
    ("Rust", rb"/rustc/[0-9a-f]{40}|rust_panic"),
    ("Nuitka (Python compiled to C)", rb"[Nn]uitka"),
    ("Microsoft Visual C++ (runtime strings)", rb"Microsoft Visual C\+\+ Runtime Library|MSVCR[0-9]{2,3}\.dll|VCRUNTIME14[0-9_]*\.dll"),
]

# name -> (string regex or None, import-name regex or None, open replacement suggestion)
MIDDLEWARE = [
    ("RenderWare", rb"RenderWare Graphics|RwEngineOpen|rwVENDORID|RenderWare", None, "librw (as re3 did)"),
    ("Bink Video", rb"BinkOpen|Bink Video|BINKW", r"^bink.*\.dll$|^binkw(32|64)\.dll$", "FFmpeg's libavcodec (has Bink decoders), or skip cutscenes"),
    ("Miles Sound System", rb"Miles Sound System|AIL_startup", r"^mss(32|64)\.dll$", "miniaudio or SDL3 audio"),
    ("FMOD", rb"FMOD Studio|FMOD Ex|FMOD::System|fmod_event", r"^fmod.*\.dll$", "miniaudio/SDL3 audio + a small reimplemented event layer"),
    ("Wwise", rb"AkSoundEngine|Audiokinetic|AK::SoundEngine", None, "miniaudio/SDL3 audio + reimplemented event/bank layer"),
    ("Havok", rb"Havok|hkBaseSystem|hkpWorld", None, "Jolt Physics or Bullet (behaviour will differ: verify against the original)"),
    ("PhysX", rb"PxCreateFoundation|PhysXLoader|NxPhysics|PhysX", r"^physx.*\.dll$|^nxcooking\.dll$", "PhysX 5 (open source, BSD-3) or Jolt"),
    ("Scaleform GFx", rb"Scaleform|GFxPlayer|GFxLoader", None, "a hand-rebuilt UI (RmlUi or immediate-mode), no SWF runtime"),
    ("Lua", rb"Lua 5\.[0-4]|lua_pushstring|LuaJIT", r"^lua.*\.dll$", "upstream Lua/LuaJIT of the same version (MIT)"),
    ("Python (embedded)", rb"Py_Initialize|PyRun_SimpleString", r"^python[0-9]+\.dll$", "CPython of the same version"),
    ("Granny 3D", rb"Granny3D|GrannyGetFileInfo", r"^granny2\.dll$", "a custom .gr2 loader (documented by community format notes)"),
    ("SpeedTree", rb"SpeedTree", None, "custom vegetation rendering or static meshes"),
    ("CRIWARE", rb"CRI Middleware|CRIWARE|criAtom|CRI ADX", None, "vgmstream/FFmpeg for ADX/HCA/USM decoding"),
    ("GameSpy", rb"gamespy|GameSpy", None, "stub it (online services are out of scope)"),
    ("OpenAL", rb"alcOpenDevice", r"^openal32\.dll$|^soft_oal\.dll$", "OpenAL Soft"),
    ("SDL", rb"SDL_Init|SDL_CreateWindow", r"^sdl[23]?\.dll$", "SDL3"),
    ("Gamebryo", rb"Gamebryo|NiNode|NiAVObject", None, "a custom scene graph + .nif loader (see community NIF docs)"),
    ("Euphoria (NaturalMotion)", rb"NaturalMotion|euphoria", None, "simplified ragdolls"),
    ("Steamworks API", None, r"^steam_api(64)?\.dll$", "stub (achievements/cloud are optional); this is not DRM by itself"),
    ("DirectDraw", None, r"^ddraw\.dll$", "SDL3 2D renderer / textures"),
    ("Direct3D 8", None, r"^d3d8\.dll$", "an SDL3 GPU / OpenGL backend behind the platform layer"),
    ("Direct3D 9", None, r"^d3d9\.dll$|^d3dx9_[0-9]+\.dll$", "an SDL3 GPU / OpenGL backend behind the platform layer"),
    ("Direct3D 10/11", None, r"^d3d1[01](_1)?\.dll$|^dxgi\.dll$", "an SDL3 GPU / Vulkan / OpenGL backend behind the platform layer"),
    ("Direct3D 12", None, r"^d3d12\.dll$", "SDL3 GPU / Vulkan backend"),
    ("OpenGL", None, r"^opengl32\.dll$|^libgl\.so", "keep OpenGL, create the context through SDL3"),
    ("Vulkan", None, r"^vulkan-1\.dll$|^libvulkan\.so", "keep Vulkan, create the surface through SDL3"),
    ("DirectInput", None, r"^dinput8?\.dll$", "SDL3 keyboard/mouse/gamepad"),
    ("XInput", None, r"^xinput.*\.dll$", "SDL3 gamepad"),
    ("DirectSound", None, r"^dsound\.dll$", "SDL3 audio streams"),
    ("XAudio2", None, r"^xaudio2.*\.dll$", "SDL3 audio / miniaudio"),
    ("Media Foundation / DirectShow video", None, r"^mf(plat|readwrite)\.dll$|^quartz\.dll$", "FFmpeg"),
    ("Winsock", None, r"^ws2_32\.dll$|^wsock32\.dll$", "SDL_net or plain sockets; stub online features"),
]

ENGINE_STRINGS = [
    ("unreal", rb"Unreal Engine|UnrealEngine|\+\+UE[345]\+Release|FEngineLoop"),
    ("idtech", rb"id Tech|idSoftware|id Software"),
    ("source", rb"VPhysics|tier0\.dll|Source Engine|vstdlib"),
    ("cryengine", rb"CryEngine|CrySystem"),
    ("renderware", rb"RenderWare"),
    ("gamebryo", rb"Gamebryo|NetImmerse"),
    ("unity", rb"UnityPlayer|UnityEngine\."),
    ("xna-fna", rb"Microsoft\.Xna\.Framework|FNA, Version|MonoGame\.Framework"),
    ("godot", rb"Godot Engine|godotengine"),
    ("electron", rb"Electron/[0-9]+\.|electron\.asar"),
    ("nwjs", rb"nw\.js|NW\.js"),
    ("air", rb"Adobe AIR|com\.adobe\.air"),
    ("python", rb"PyInstaller|py2exe|PYTHONSCRIPT|cx_Freeze|__startup__"),
]

DOTNET_PROTECTORS = [
    ("ConfuserEx", rb"ConfuserEx|ConfusedByAttribute"), ("Dotfuscator", rb"DotfuscatorAttribute|PreEmptive"),
    (".NET Reactor", rb"\.NET Reactor|Eziriz"), ("SmartAssembly", rb"SmartAssembly\.Attributes|PoweredByAttribute"),
    ("Eazfuscator.NET", rb"Eazfuscator"), ("Babel Obfuscator", rb"BabelObfuscatorAttribute|BabelAttribute"),
    ("Agile.NET / CliSecure", rb"AgileDotNet|CliSecure"), ("Obfuscar", rb"Obfuscar"),
]

PROTECTOR_STRINGS = [
    ("Denuvo", rb"[Dd]enuvo", "drm", 70), ("Arxan", rb"Arxan|GuardIT", "protector", 60),
    ("SecuROM", rb"SecuROM", "drm", 70), ("SafeDisc", rb"SafeDisc|BoG_ \*90\.0&!!  Yy>", "drm", 70),
    ("StarForce", rb"StarForce|protect\.dll", "drm", 60), ("Themida/WinLicense", rb"Themida|WinLicense|Oreans", "protector", 60),
    ("VMProtect", rb"VMProtect", "protector", 60), ("EasyAntiCheat", rb"EasyAntiCheat", "anti-cheat", 70),
    ("BattlEye", rb"BattlEye|BEClient", "anti-cheat", 70), ("Steam CEG", rb"SteamDRM|CEG_", "drm", 40),
]


def grep_signals(f, size: int, budget: int = STRING_BUDGET) -> dict[str, list[tuple[str, str]]]:
    """One pass over (up to) `budget` bytes. Returns {group: [(name, first match)]}."""
    groups = {"compiler": [(n, p) for n, p in COMPILER_STRINGS],
              "middleware": [(n, p) for n, p, _, _ in MIDDLEWARE if p],
              "engine": ENGINE_STRINGS, "dotnet_protector": [(n, p) for n, p in DOTNET_PROTECTORS],
              "protector": [(n, p) for n, p, _, _ in PROTECTOR_STRINGS]}
    compiled = {g: [(n, re.compile(p)) for n, p in items] for g, items in groups.items()}
    found: dict[str, dict[str, str]] = {g: {} for g in groups}
    f.seek(0)
    chunk, overlap, read = 8 << 20, 256, 0
    prev = b""
    while read < min(size, budget):
        data = f.read(chunk)
        if not data:
            break
        buf = prev + data
        for g, items in compiled.items():
            for n, rx in items:
                if n in found[g]:
                    continue
                m = rx.search(buf)
                if m:
                    found[g][n] = m.group(0).decode("latin-1", errors="replace")[:80]
        prev = data[-overlap:]
        read += len(data)
    return {g: list(v.items()) for g, v in found.items()}


# --------------------------------------------------------------------------- one file

def analyze(path: Path, deep: bool = True) -> dict:
    info: dict
    size = path.stat().st_size
    with open(path, "rb") as f:
        head = f.read(HEAD)
        if size > TAIL:
            f.seek(-TAIL, io.SEEK_END)
            tail = f.read(TAIL)
        else:
            tail = head
        info = (sniff_pe(head, f, size) or sniff_elf(head, f, size) or sniff_macho(head, f, size) or sniff_xbe(head, f, size)
                or sniff_xex(head, f, size) or sniff_sce(head, f, size) or sniff_switch(head, f, size, path)
                or sniff_rom(head, f, size, path) or sniff_dol(head, f, size, path) or sniff_misc(head, tail, f, size, path)
                or (sniff_disc(f, size, path) if size > 0x9400 else None))
        if info is None:
            info = {"format": "unknown", "arch": "unknown", "bits": 0, "endian": "unknown", "entropy": round(entropy(head[:1 << 16]), 2)}
        info = {"path": str(path), "size": size, **info}
        executable = info["format"].startswith(("PE", "ELF", "Mach-O", "XBE", "XEX", "DOL", "NSO", "NRO", "PS-X", "MZ"))
        if executable or info["format"].startswith(("Nintendo", "Game Boy")):
            payloads = appended_payloads(head, tail, f, size) if executable else []
            if payloads:
                info["appended"] = payloads
            if deep:
                sig = grep_signals(f, size)
                info["_strings"] = sig
                if size > 2 * STRING_BUDGET:
                    info["strings_truncated"] = True
            if info["format"].startswith("PE"):
                overlay = read_at(f, size - min(size, 1 << 20), min(size, 1 << 20)) if info.get("overlay_bytes") else b""
                blob = head + overlay
                for name, pat in (("Inno Setup installer", b"Inno Setup Setup Data"), ("NSIS installer", b"Nullsoft"),
                                  ("InstallShield installer", b"InstallShield"), ("WiX Burn bundle", b".wixburn")):
                    if pat in blob or (name.startswith("WiX") and ".wixburn" in info.get("sections", [])):
                        info["installer"] = name
                        break
                if info.get("overlay_bytes") and not info.get("installer"):
                    probe = read_at(f, size - info["overlay_bytes"], 16)
                    if probe.startswith(b"7z\xbc\xaf") or probe.startswith(b"Rar!"):
                        info["installer"] = "self-extracting archive"
            if head[:2] == b"MZ" and DOTNET_BUNDLE_SIG in head + tail:
                info["dotnet_bundle"] = True
            elif head[:2] == b"MZ" and size < (64 << 20):
                f.seek(0)
                if DOTNET_BUNDLE_SIG in f.read():
                    info["dotnet_bundle"] = True
    return info
