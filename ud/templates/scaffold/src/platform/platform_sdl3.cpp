// SDL3 backend.
#include "platform/platform.h"

#include <SDL3/SDL.h>

#include "platform/platform_common.inl"

namespace platform {

static SDL_Window* g_window = nullptr;
static SDL_Renderer* g_renderer = nullptr;
static SDL_Texture* g_texture = nullptr;
static int g_tex_w = 0, g_tex_h = 0;

bool init(const Config& cfg) {
    if (cfg.headless) SDL_SetHint(SDL_HINT_VIDEO_DRIVER, "dummy");
    if (!SDL_Init(SDL_INIT_VIDEO | SDL_INIT_EVENTS)) {
        log("SDL_Init failed: %s", SDL_GetError());
        return false;
    }
    if (!SDL_CreateWindowAndRenderer(cfg.title, cfg.width, cfg.height, 0, &g_window, &g_renderer)) {
        log("SDL_CreateWindowAndRenderer failed: %s", SDL_GetError());
        return false;
    }
    return true;
}

void shutdown() {
    if (g_texture) SDL_DestroyTexture(g_texture);
    if (g_renderer) SDL_DestroyRenderer(g_renderer);
    if (g_window) SDL_DestroyWindow(g_window);
    g_texture = nullptr;
    g_renderer = nullptr;
    g_window = nullptr;
    SDL_Quit();
}

bool pump_events() {
    SDL_Event e;
    while (SDL_PollEvent(&e)) {
        if (e.type == SDL_EVENT_QUIT) return false;
    }
    return true;
}

bool key_down(Key k) {
    static const SDL_Scancode map[] = {SDL_SCANCODE_UP, SDL_SCANCODE_DOWN, SDL_SCANCODE_LEFT,
                                       SDL_SCANCODE_RIGHT, SDL_SCANCODE_RETURN, SDL_SCANCODE_ESCAPE};
    const bool* state = SDL_GetKeyboardState(nullptr);
    return state && state[map[static_cast<int>(k)]];
}

void present(const uint32_t* rgba, int width, int height) {
    if (!g_renderer) return;
    if (!g_texture || g_tex_w != width || g_tex_h != height) {
        if (g_texture) SDL_DestroyTexture(g_texture);
        g_texture = SDL_CreateTexture(g_renderer, SDL_PIXELFORMAT_RGBA32, SDL_TEXTUREACCESS_STREAMING, width, height);
        g_tex_w = width;
        g_tex_h = height;
    }
    SDL_UpdateTexture(g_texture, nullptr, rgba, width * 4);
    SDL_RenderClear(g_renderer);
    SDL_RenderTexture(g_renderer, g_texture, nullptr, nullptr);
    SDL_RenderPresent(g_renderer);
}

uint64_t ticks_ms() { return SDL_GetTicks(); }
void sleep_ms(uint32_t ms) { SDL_Delay(ms); }

}  // namespace platform
