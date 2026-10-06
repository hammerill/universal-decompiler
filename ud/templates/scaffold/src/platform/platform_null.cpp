// Headless backend: no window, no input. Deterministic time is up to the caller.
#include "platform/platform.h"

#include <chrono>
#include <thread>

#include "platform/platform_common.inl"

namespace platform {

static std::chrono::steady_clock::time_point g_start;

bool init(const Config&) {
    g_start = std::chrono::steady_clock::now();
    return true;
}
void shutdown() {}
bool pump_events() { return true; }
bool key_down(Key) { return false; }
void present(const uint32_t*, int, int) {}
uint64_t ticks_ms() {
    return static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - g_start).count());
}
void sleep_ms(uint32_t ms) { std::this_thread::sleep_for(std::chrono::milliseconds(ms)); }

}  // namespace platform
