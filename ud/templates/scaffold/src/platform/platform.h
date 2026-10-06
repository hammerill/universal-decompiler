// Thin platform layer: everything the reconstructed code needs from the OS (window, input, time, audio,
// files) goes through here. The original's Win32/D3D/DirectInput/console-SDK calls are reimplemented on top
// of it, never called directly from game code. Backends: platform_sdl3.cpp (default), platform_null.cpp
// (headless: CI, tests, oracle comparisons).
#pragma once
#include <cstdint>
#include <string>

namespace platform {

struct Config {
    const char* title = "reconstruction";
    int width = 640;
    int height = 480;
    bool headless = false;   // no window (CI / oracle runs)
};

enum class Key { Up, Down, Left, Right, Confirm, Cancel, Count };

bool init(const Config& cfg);
void shutdown();

// Pump OS events; false once the user asked to quit.
bool pump_events();
bool key_down(Key k);

// Present a 32-bit RGBA framebuffer (width*height pixels).
void present(const uint32_t* rgba, int width, int height);

uint64_t ticks_ms();
void sleep_ms(uint32_t ms);

// Where extracted assets live (data/ next to the working directory unless UD_DATA_DIR is set).
std::string data_path(const std::string& relative);

void log(const char* fmt, ...);

}  // namespace platform
