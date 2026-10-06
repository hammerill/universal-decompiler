// Text assets: rules.txt (key=value) and strings.txt (one message per line).
#include <cstdio>
#include <cstring>

#include "game/world.h"

namespace game {

namespace {

// Advance past the current line (and its '\n', if any).
const char* next_line(const char* p) {
    while (*p && *p != '\n') ++p;
    return *p ? p + 1 : p;
}

}  // namespace

// 0x00401D11  parse_rules
// Defaults first, then every "key=value" line that sscanf("%31[^=]=%d") accepts; unknown keys are ignored.
void parse_rules(Rules& r, const char* text) {
    r = Rules{};
    for (const char* p = text; *p; p = next_line(p)) {
        char key[32];
        int value = 0;
        if (std::sscanf(p, "%31[^=]=%d", key, &value) != 2) continue;
        if (std::strcmp(key, "hp") == 0) r.hp = value;
        else if (std::strcmp(key, "coin_score") == 0) r.coin_score = value;
        else if (std::strcmp(key, "exit_bonus") == 0) r.exit_bonus = value;
        else if (std::strcmp(key, "enemy_damage") == 0) r.enemy_damage = value;
        else if (std::strcmp(key, "chase_radius") == 0) r.chase_radius = value;
    }
}

// 0x004018E5  parse_strings
// Up to 8 lines, each truncated to 47 characters. Stops at the end of the text, or at a trailing empty line.
void parse_strings(World& w, const char* text) {
    w.string_count = 0;
    const char* p = text;
    while (*p && w.string_count < kMaxStrings) {
        size_t n = 0;
        while (p[n] && p[n] != '\n') ++n;
        const size_t c = n < kStringLen - 1 ? n : kStringLen - 1;
        std::memcpy(w.strings[w.string_count], p, c);
        w.strings[w.string_count][c] = '\0';
        ++w.string_count;
        p += n;
        if (*p) ++p;
    }
}

// 0x00401E62  say
// Prints message `id` indented by two spaces; ids past the loaded strings print nothing.
void say(const World& w, int id) {
    if (id < w.string_count) std::printf("  %s\n", w.strings[id]);
}

}  // namespace game
