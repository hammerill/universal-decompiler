# C++ and CMake conventions for reconstructions

## Baseline
- **C++17 minimum, CMake 3.20 or newer.** Builds with MSVC on Windows, GCC or Clang on Linux and Apple Clang
  on macOS; CI-style check on all three before claiming done.
- **Release target: 64-bit on every OS** (Windows x64, Linux x86-64, macOS arm64; x86-64 or a universal
  binary on request, see below). A 32-bit build is allowed only as an
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
  `long` is 32-bit on Windows and 64-bit on Linux and macOS: never use it for on-disk data.
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
- **`wchar_t`** is 16-bit on Windows, 32-bit on Linux and macOS: use `char16_t`/UTF-8 for text from the original's data.
- **Time and randomness**: replace `GetTickCount`/`timeGetTime`/`rand()` behind the platform layer, and keep
  the original's RNG algorithm when its sequence is observable.

## macOS (Apple Clang, arm64)
The same CMake project builds on macOS with the Xcode Command Line Tools (`xcode-select --install`: Apple
Clang, libc++, git) and CMake, with the Linux command line (`cmake -S . -B build -DCMAKE_BUILD_TYPE=Release`).
The build is native (arm64 on Apple silicon); `-DCMAKE_OSX_ARCHITECTURES="arm64;x86_64"` makes a universal
binary, and Rosetta 2 runs an x86-64 build when you need to rule out the architecture. SDL3 fetched by
CMake builds its Cocoa, Metal and CoreAudio backends with nothing else installed. A code base that builds
with GCC usually needs only small fixes:
- **Clang rejects what GCC only warns about**, and decompiled or 2000s-era code has plenty of it:
  - `register` is ill-formed in C++17 (Clang: error, GCC: warning). Delete the keyword.
  - Narrowing a non-constant inside braces is an error in Clang (`-Wc++11-narrowing`), a warning in GCC:
    `float px[4] = { 0, rect.mWidth }` with an `int` field, `char s[2] = { code - 0x80, 0 }`. Add the
    explicit cast, and cast the result of the expression, not an operand, so the value stays the original's.
  - Build on macOS early (or with Clang on Linux) instead of collecting these at the end.
- **Missing glibc-isms:** `<malloc.h>` (use `<cstdlib>`), `<endian.h>`/`<byteswap.h>` (write the swap or use
  `__builtin_bswap32`), `fopen64`/`off64_t`/`lseek64` (the plain ones are 64-bit already), `memalign`
  (`posix_memalign`), unnamed POSIX semaphores (`sem_init` fails on macOS: use `std::condition_variable` or
  SDL's semaphores), `pthread_setname_np(thread, name)` (macOS takes only the name, for the calling thread).
- **arm64 is not x86:** inline assembly, `<xmmintrin.h>`/SSE intrinsics, `__rdtsc`, `_controlfp` and other
  x87 control-word tricks don't exist. Port them to plain C++ (keep x86 fast paths behind
  `#if defined(__x86_64__) || defined(_M_X64)` if they matter). Clang fuses `a * b + c` into one
  multiply-add on arm64, which changes the last bits of float results: build with `-ffp-contract=off` when
  the oracle compares floats.
- **`char` is signed** on macOS arm64 (Apple's ABI keeps the x86 choice), like the MSVC original; it is
  unsigned on Linux arm64, so a Linux arm64 build needs `-fsigned-char` or explicit `signed char`.
- **Per-user data** goes to `~/Library/Application Support/<org>/<app>/`: `SDL_GetPrefPath` returns it, so
  don't hardcode `~/.local/share`. APFS is case-insensitive by default but can be formatted case-sensitive:
  keep the case-insensitive asset lookup instead of relying on it.
- **Linking:** executables are always position-independent (drop `-no-pie`), Apple's `ld` calls `-s`
  obsolete (use `-Wl,-x` or `strip`), and arm64 binaries must be code-signed: the linker signs ad hoc by
  itself, so re-sign (`codesign -s - -f <exe>`) only after patching a binary. A plain executable runs from
  the terminal, and that is the default macOS output (see "App bundle" below for the on-request one).
- **Debugging:** `lldb` (GDB doesn't run on Apple silicon); AddressSanitizer works with Apple Clang.

### App bundle (only when the user asks)
The default build stays a bare executable (`build/<dir>/bin/<name>`), as on Linux: `ud build`, `ud run` and
the oracle comparisons use it, and the done criterion doesn't need more. When the user wants a
double-clickable Mac application, add a separate `app` target in an `if(APPLE)` block instead of putting
`MACOSX_BUNDLE` on the main target (which would move the executable into `.app/Contents/MacOS/` for every
build). `cmake --build build/mac --target app` then makes `build/mac/<Title>.app`:
- **`add_custom_target(app ... DEPENDS <exe> VERBATIM)`** that deletes and recreates the bundle each time:
  `Contents/MacOS/<exe>` (`$<TARGET_FILE:...>`), `Contents/Info.plist`, the game's files under
  `Contents/Resources/`, the icon, then `codesign --force --sign - "<bundle>"`. Sign last: changing anything
  in the bundle afterwards breaks the signature, and arm64 refuses to run it.
- **`Info.plist`** from `cmake/Info.plist.in` with `configure_file(... @ONLY)`: `CFBundleExecutable` =
  the target name, `CFBundleIconFile`, `CFBundleIdentifier` (a local one, like `local.<project>`, never the
  original publisher's), `CFBundlePackageType` `APPL`, version strings from the original's version,
  `LSMinimumSystemVersion` = the deployment target, `NSHighResolutionCapable` true.
- **Deployment target:** set `CMAKE_OSX_DEPLOYMENT_TARGET` (e.g. `11.0`, the first arm64 macOS) as a cache
  variable *before* `project()`; otherwise the binary only runs on the build machine's macOS version or newer.
- **Game files:** copy only the folders the program reads, from `data/` (overridable cache path), into
  `Contents/Resources/`. Inside a bundle `SDL_GetBasePath()` returns `Contents/Resources/`, so a game-folder
  search that already checks "next to the executable" through `SDL_GetBasePath()` finds them unchanged.
  Per-user files still go to `SDL_GetPrefPath`; the bundle is read-only once signed.
- **Icon:** a small `uv run tools/make_icon.py <data> <out.icns>` script (PEP 723, Pillow, which writes ICNS)
  that builds a 1024x1024 icon from the user's own copy: the original's icon resource, or a sprite from its
  data (artwork about 80% of the canvas). Run it from the `app` target if `uv` is found, otherwise skip the
  icon with a `message(STATUS ...)` rather than failing.
- **It contains the original's assets:** keep it under the ignored `build/`, never commit or publish it, and
  don't hand it to anyone else. The ad-hoc signature makes it run on the Mac that built it; on another Mac
  Gatekeeper blocks it until right-click > Open (or `xattr -dr com.apple.quarantine <bundle>`).
- Document the target in the reconstruction's README ("macOS app") with what it needs (`uv` for the icon)
  and what it doesn't do (no notarisation, single architecture unless `CMAKE_OSX_ARCHITECTURES` says so).

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
