# The platform layer

Everything the reconstructed program needs from the OS or the console goes through one thin interface.
Game code never calls Win32, Direct3D, DirectInput, DirectSound, POSIX or a console SDK directly; those
calls are reimplemented as functions of the layer. Default backend: **SDL3** (current major version; 3.4.x
in October 2026). `ud init --scaffold` writes a starting point: `src/platform/platform.h`, an SDL3 backend
and a headless null backend.

## Why a layer
- One place to port: Windows, Linux and macOS (and anything SDL3 supports) from the same game code.
- A headless backend for CI and oracle runs (`--headless`, fixed time step, no window).
- Faithful timing and input semantics can be emulated in one spot instead of all over the game code.

## Interface shape (keep it small)
```cpp
namespace platform {
bool init(const Config&);  void shutdown();
bool pump_events();        bool key_down(Key);  // + mouse, gamepad as the program needs
void present(const uint32_t* rgba, int w, int h);  // or a renderer interface, see below
uint64_t ticks_ms();       void sleep_ms(uint32_t);
std::string data_path(const std::string& rel);     // data/ unless UD_DATA_DIR is set
bool read_file(const std::string& path, std::vector<uint8_t>& out);
void log(const char* fmt, ...);
}
```
Grow it only when a module needs something new; name functions after the need ("present a frame"), not
after the original API ("IDirect3DDevice9::Present").

## Mapping common original APIs
| Original | Platform layer / SDL3 |
|---|---|
| `WinMain`, message loop (`PeekMessage`/`DispatchMessage`) | `main` + `pump_events()` (SDL_PollEvent) |
| `CreateWindowEx`, display modes | `init()`: SDL_CreateWindow, SDL_SetWindowFullscreen |
| DirectDraw surfaces, palettised 8-bit framebuffers | a CPU framebuffer converted to RGBA, then `present()` (SDL streaming texture) |
| Direct3D 8/9, OpenGL 1.x fixed function | a renderer interface implemented on SDL3's GPU API or OpenGL 3.3; emulate fixed-function state (transforms, texture stages, fog) in shaders |
| Direct3D 10/11/12, Vulkan | SDL3 GPU API (or keep Vulkan via SDL_Vulkan_CreateSurface) |
| DirectInput, raw input, XInput | SDL keyboard state, mouse, SDL gamepad API |
| DirectSound, XAudio2, waveOut, Miles, FMOD playback | SDL audio streams (or miniaudio) with a small mixer in the layer |
| `GetTickCount`, `timeGetTime`, `QueryPerformanceCounter` | `ticks_ms()` / a high-resolution counter (SDL_GetTicksNS); keep the original's frame pacing |
| `CreateFile`/`fopen` with `\` paths, case-insensitive names | `read_file()` + path normalisation; Linux (and case-sensitive macOS volumes) need case-insensitive lookup for data from Windows games |
| Registry settings, `%APPDATA%` saves | a config file in the per-user folder from `SDL_GetPrefPath` (`%APPDATA%`, `~/.local/share`, `~/Library/Application Support`) |
| `MessageBox` | SDL_ShowSimpleMessageBox |
| Threads, critical sections | `std::thread`, `std::mutex` |
| Winsock, DirectPlay, GameSpy | sockets behind the layer for LAN play; stub online services |

## Consoles
The layer replaces the console SDK and hardware: graphics command lists (GX on GameCube/Wii, GS packets on
PS2, the RSP/RDP display lists on N64, Xenos on Xbox 360) become calls into a renderer backend; pad
reading becomes SDL gamepad input; memory cards become save files under the user's config folder; the
console's fixed frame rate becomes the platform's frame pacing. Recompilation runtimes (N64ModernRuntime,
the XenonRecomp-based runtimes) are this layer for their platform: reuse them when the route is
recompilation.

## Rules
- Behaviour first: if the original polls input once per frame at a fixed 30 Hz, the layer reproduces that,
  even if SDL could do better. Enhancements (higher frame rates, widescreen) come after verification and
  are switchable.
- Keep a null/headless backend building at all times; the oracle comparisons run on it.
- Record in `DECOMP_PLAN.md` which original APIs the layer replaces.
