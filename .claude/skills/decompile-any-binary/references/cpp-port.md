# C++ and CMake conventions for reconstructions

## Baseline
- **C++17 minimum, CMake 3.20 or newer.** Builds with MSVC on Windows and GCC or Clang on Linux; CI-style
  check on both before claiming done.
- **Release target: 64-bit on both OSes** (Windows x64, Linux x86-64). A 32-bit build is allowed only as an
  intermediate step (the hybrid route's DLL injected into a 32-bit original). The CMake skeleton warns on
  32-bit builds.
- One predictable output folder: `build/bin/<target>[.exe]` (`RUNTIME_OUTPUT_DIRECTORY
  "${CMAKE_BINARY_DIR}/bin/$<0:>"` stops multi-config generators from adding `Release/`). `ud run` looks
  there.
- Warnings on (`/W4 /permissive- /utf-8` on MSVC, `-Wall -Wextra` elsewhere); fix them, many are real
  portability bugs.

## Layout
```
CMakeLists.txt
src/main.cpp                 the original's entry point (WinMain/main)
src/<module>/*.cpp|h         one folder per module from DECOMP_PLAN.md's module map
src/platform/platform.h      the thin platform interface (see platform-layer.md)
src/platform/platform_sdl3.cpp, platform_null.cpp
third_party/                 open replacements for middleware (fetched by CMake when possible)
tools/extract_assets.py      PEP 723 script, reads the user's copy, writes data/
decomp/progress.json         ud funcs
```

## Every function keeps its address
```cpp
// 0x00401F0E  move_player  (original: FUN_00401f0e)
void move_player(World& w, char cmd) { ... }
```
The comment is the link back to Ghidra and to `decomp/progress.json`. Keep it when you refactor; if two
originals merge into one function, list both addresses.

## Idiomatic but behaviour-faithful
- Name things for what they do; replace pointer arithmetic on raw offsets with structs (document the
  original offsets in comments, as `examples/tinyquest/reconstruction/src/game/world.h` does).
- Keep the **observable behaviour** identical: iteration order, RNG call order and count, integer widths and
  signedness, rounding, float precision, the order of side effects (sounds, log lines), off-by-one quirks.
  Fix an original bug only on purpose, write it down in `DECOMPLOG.md`, and make it switchable if it
  affects gameplay (`#if UD_FIX_ORIGINAL_BUGS`).
- RAII, `std::vector`, `std::string`, `std::array` and enums where they don't change behaviour; keep fixed-size
  arrays when the original's limits are observable (max entities, string lengths).
- Don't "modernise" the algorithm while porting. First faithful, verified; refactor later with the oracle as
  a safety net.

## Decompiler output -> C++: the usual translations
| Decompiler shows | Usually means |
|---|---|
| `*(int *)(param_1 + 0xe8)` | a struct field at offset 0xE8: define the struct (Ghidra: create it and retype `param_1`) |
| `uVar1 >> 0x1f`, `iVar >> 0x1f` | sign extraction from a comparison (`x < 0`), or `~x >> 31` = `x >= 0` |
| `(uint)(x < 0x14) && ...` on an `int` | an unsigned compare doing a bounds check `0 <= x < 20` |
| `x * 0x41c64e6d + 0x3039` | the ANSI C LCG (1103515245, 12345) |
| `0x811c9dc5`, `0x1000193` | FNV-1a 32-bit |
| long chains of `goto LAB_...` | an optimised `if/else if` or `switch`: rebuild the condition table, then test it against the original |
| inlined `memcpy`/`memset`/`strlen` sequences | the library call; check sizes and terminators |
| `in_FS_OFFSET + 0x28` / `__security_cookie` | the stack protector: drop it |
| `__thiscall`, first argument `this` in ECX (x86) | a member function: rebuild the class and its vtable |

## 32 -> 64-bit pitfalls
- **Pointer size in data structures.** Structs read from files or memory dumps with 32-bit pointers or `long`
  fields: use explicit `uint32_t` offsets in the file format and convert to pointers after loading.
  `long` is 32-bit on Windows and 64-bit on Linux: never use it for on-disk data.
- **Pointers stored in ints** (handles, IDs, callbacks in 32-bit fields): use `uintptr_t` or an index table.
- **`size_t` vs `int` arithmetic**: negative values and comparisons change meaning; keep the original's
  signedness in loops that the oracle observes.
- **Struct packing and alignment**: MSVC and GCC agree on natural alignment for x64, but `#pragma pack`
  structures in the original must stay packed; read files field by field instead of `fread` into a struct.
- **x87 vs SSE floats**: 32-bit originals often computed in 80-bit x87 registers. Results can differ in the
  last bits; where the oracle notices (physics, replays), use `double` intermediates or replicate the
  original's float order, and compare traces.
- **Calling conventions** disappear on x64 (`__stdcall`/`__fastcall` are ignored): fine for the clean
  rewrite, but the hybrid DLL must match them exactly while it's still 32-bit.
- **`wchar_t`** is 16-bit on Windows, 32-bit on Linux: use `char16_t`/UTF-8 for text from the original's data.
- **Time and randomness**: replace `GetTickCount`/`timeGetTime`/`rand()` behind the platform layer, and keep
  the original's RNG algorithm when its sequence is observable.

## The hybrid route (DLL injection), in CMake
- A `SHARED` library target built for the original's architecture (`-A Win32` with MSVC for 32-bit
  originals), plus a small loader: a proxy DLL the original already imports (`dinput8.dll`, `winmm.dll`,
  `version.dll`...) or an import-table patch of a *copy* of the executable in `data/`.
- Each reimplemented function is installed with a detour (MinHook, SafetyHook) at its original address; a
  table maps addresses to replacements so one can be switched off to bisect a bug against the original.
- The DLL is an intermediate artefact: once the tracker shows the important modules ported, add the
  standalone 64-bit target (`main.cpp` + platform layer) and keep both building until the standalone one
  meets the done criterion.

## Middleware
Replace proprietary middleware with open equivalents with the same API when they exist (librw for
RenderWare, as re3 did; OpenAL Soft; Lua/LuaJIT of the same version; PhysX 5 under BSD-3), otherwise
reimplement the subset the program uses, or stub it (online services, DRM-adjacent launchers). Record
every replacement in `DECOMP_PLAN.md`'s middleware table. `ud scan` suggests a replacement for each
middleware it recognises.
