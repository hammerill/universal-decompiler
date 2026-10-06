// Vertical-slice entry point. Replace the body with the reconstructed WinMain/main flow, keeping every
// reconstructed function's original address in a comment, e.g.:
//   // 0x00401A30  Game::Init  (original: FUN_00401a30)
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

#include "platform/platform.h"

int main(int argc, char** argv) {
    platform::Config cfg;
    long frames = -1;   // -1: run until the window closes
    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--headless") == 0) cfg.headless = true;
        else if (std::strcmp(argv[i], "--frames") == 0 && i + 1 < argc) frames = std::strtol(argv[++i], nullptr, 10);
    }
    if (!platform::init(cfg)) return 1;
    std::vector<uint32_t> fb(static_cast<size_t>(cfg.width) * cfg.height);
    for (long f = 0; frames < 0 || f < frames; ++f) {
        if (!platform::pump_events() || platform::key_down(platform::Key::Cancel)) break;
        for (int y = 0; y < cfg.height; ++y)
            for (int x = 0; x < cfg.width; ++x)
                fb[static_cast<size_t>(y) * cfg.width + x] = 0xff000000u | ((x + f) & 0xff) | (((y + f) & 0xff) << 8);
        platform::present(fb.data(), cfg.width, cfg.height);
        platform::sleep_ms(16);
    }
    std::printf("vertical slice ok\n");
    platform::shutdown();
    return 0;
}
