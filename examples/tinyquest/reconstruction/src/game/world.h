// Game state. Layout recovered from the global at 0x004080E0 in the original (offsets in comments); the
// reconstruction doesn't depend on the layout, the offsets document where each field was found.
#pragma once
#include <cstdint>

namespace game {

constexpr int kMapW = 20;           // is_wall bound check: x < 0x14
constexpr int kMapH = 11;           // y < 0xb; rows are 0x15 bytes apart (20 chars + NUL)
constexpr int kMaxEnemies = 8;      // load_level stops adding enemies at 8
constexpr int kMaxStrings = 8;      // parse_strings stops at 8 lines
constexpr int kStringLen = 48;      // 0x30-byte slots, 47 chars + NUL

struct Rules {                      // +0x2EC
    int hp = 3;                     // defaults set by parse_rules before reading rules.txt
    int coin_score = 1;
    int exit_bonus = 0;
    int enemy_damage = 1;
    int chase_radius = 3;
};

struct Enemy {                      // 12 bytes each, array at +0xFC
    int x = 0, y = 0;
    bool alive = false;             // stored as int in the original
};

enum class Outcome : int { Running = 0, Exit = 1, Dead = 2, OutOfTime = 3 };

struct World {
    char tiles[kMapH][kMapW + 1] = {};  // +0x000
    int px = -1, py = -1;               // +0x0E8, +0x0EC
    int hp = 0;                         // +0x0F0
    int score = 0;                      // +0x0F4
    int coins_left = 0;                 // +0x0F8
    Enemy enemies[kMaxEnemies];         // +0x0FC
    int enemy_count = 0;                // +0x15C
    uint32_t rng = 0;                   // +0x160
    Outcome outcome = Outcome::Running; // +0x164
    char strings[kMaxStrings][kStringLen] = {};  // +0x168
    int string_count = 0;               // +0x2E8
    Rules rules;                        // +0x2EC
};

// Message ids: lines of strings.txt.
enum Msg { kTitle = 0, kHitWall = 1, kCoin = 2, kBitten = 3, kExit = 4, kFallen = 5, kOutOfTime = 6 };

void parse_rules(Rules& r, const char* text);
void parse_strings(World& w, const char* text);
bool load_level(World& w, const char* text);

void say(const World& w, int id);
void tick(World& w, char cmd);
uint32_t world_hash(const World& w);
void render(const World& w);

}  // namespace game
