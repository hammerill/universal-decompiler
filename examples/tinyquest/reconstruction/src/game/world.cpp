// Level loading and the simulation tick.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>

#include "game/world.h"

namespace game {

namespace {

// Enemy wander directions, indexed by rng % 4: up, right, down, left.
// Tables at 0x00403180 (dx) and 0x00403170 (dy) in the original.
constexpr int kWanderDx[4] = {0, 1, 0, -1};
constexpr int kWanderDy[4] = {-1, 0, 1, 0};

// 0x004013B5  rng_next
// The classic ANSI C LCG (a = 1103515245, c = 12345), returning bits 16..30.
uint32_t rng_next(World& w) {
    w.rng = w.rng * 1103515245u + 12345u;
    return (w.rng >> 16) & 0x7fff;
}

// 0x004014EC  is_wall
// Everything outside the 20x11 map counts as wall.
bool is_wall(const World& w, int x, int y) {
    if (x < 0 || y < 0 || x >= kMapW || y >= kMapH) return true;
    return w.tiles[y][x] == '#';
}

int sign(int v) { return v > 0 ? 1 : (v < 0 ? -1 : 0); }

// 0x00401E9B  bite_check
// Every live enemy standing on the player bites once.
void bite_check(World& w) {
    for (int i = 0; i < w.enemy_count; ++i) {
        const Enemy& e = w.enemies[i];
        if (e.alive && e.x == w.px && e.y == w.py) {
            w.hp -= w.rules.enemy_damage;
            say(w, kBitten);
        }
    }
}

// 0x00401F0E  move_player
// U/D/L/R move one tile; any other command waits. Walls block (and print a message); coins and the exit
// trigger on entry.
void move_player(World& w, char cmd) {
    int dx = 0, dy = 0;
    switch (cmd) {
        case 'U': dy = -1; break;
        case 'D': dy = 1; break;
        case 'L': dx = -1; break;
        case 'R': dx = 1; break;
        default: return;
    }
    const int nx = w.px + dx, ny = w.py + dy;
    if (is_wall(w, nx, ny)) {
        say(w, kHitWall);
        return;
    }
    w.px = nx;
    w.py = ny;
    char& t = w.tiles[ny][nx];
    if (t == '$') {
        t = '.';
        w.score += w.rules.coin_score;
        --w.coins_left;
        say(w, kCoin);
    } else if (t == 'X') {
        w.score += w.rules.exit_bonus;
        w.outcome = Outcome::Exit;
        say(w, kExit);
    }
}

// 0x00401518  move_enemies
// Within chase_radius (Manhattan distance) an enemy steps toward the player: along x when |dx| >= |dy|,
// else along y, falling back to the other axis when blocked. Farther away it wanders: one rng draw per
// enemy, and it stays put if the target is a wall or the exit. The rng is only consumed by wanderers,
// which makes the order of enemies part of the observable behaviour.
void move_enemies(World& w) {
    for (int i = 0; i < w.enemy_count; ++i) {
        Enemy& e = w.enemies[i];
        if (!e.alive) continue;
        const int ddx = w.px - e.x, ddy = w.py - e.y;
        const int adx = std::abs(ddx), ady = std::abs(ddy);
        int nx = e.x, ny = e.y;
        if (adx + ady <= w.rules.chase_radius) {
            const int sx = sign(ddx), sy = sign(ddy);
            if (adx >= ady && sx != 0 && !is_wall(w, e.x + sx, e.y)) nx = e.x + sx;
            else if (sy != 0 && !is_wall(w, e.x, e.y + sy)) ny = e.y + sy;
            else if (sx != 0 && !is_wall(w, e.x + sx, e.y)) nx = e.x + sx;
        } else {
            const uint32_t d = rng_next(w) % 4;
            nx = e.x + kWanderDx[d];
            ny = e.y + kWanderDy[d];
            if (is_wall(w, nx, ny) || w.tiles[ny][nx] == 'X') {
                nx = e.x;
                ny = e.y;
            }
        }
        e.x = nx;
        e.y = ny;
    }
}

}  // namespace

// 0x004013D3  load_level
// Rows end at '\n'; characters past column 20 are dropped. '@' sets the player start, 'E' spawns an enemy
// (both leave floor behind), '$' is counted. Returns false when the level has no player.
bool load_level(World& w, const char* text) {
    w.enemy_count = 0;
    w.coins_left = 0;
    w.px = w.py = -1;
    int x = 0, y = 0;
    for (const char* p = text; *p && y < kMapH; ++p) {
        if (*p == '\n') {
            w.tiles[y][x] = '\0';
            ++y;
            x = 0;
            continue;
        }
        if (x >= kMapW) continue;
        char c = *p;
        if (c == '@') {
            w.px = x;
            w.py = y;
            c = '.';
        } else if (c == 'E' && w.enemy_count < kMaxEnemies) {
            w.enemies[w.enemy_count++] = Enemy{x, y, true};
            c = '.';
        } else if (c == '$') {
            ++w.coins_left;
        }
        w.tiles[y][x++] = c;
    }
    return w.px >= 0;
}

// 0x0040200C  tick
// Player first; if that ended the game nothing else happens. Then bites, enemy moves, bites again.
void tick(World& w, char cmd) {
    move_player(w, cmd);
    if (w.outcome != Outcome::Running) return;
    bite_check(w);
    move_enemies(w);
    bite_check(w);
    if (w.hp <= 0) {
        w.outcome = Outcome::Dead;
        say(w, kFallen);
    }
}

// 0x0040173D  world_hash
// 32-bit FNV-1a over px, py, hp, score, then x*64+y of every enemy (dead ones too), then the 20x11 tiles.
uint32_t world_hash(const World& w) {
    uint32_t h = 2166136261u;
    auto mix = [&h](uint32_t v) { h = (h ^ v) * 16777619u; };
    for (int v : {w.px, w.py, w.hp, w.score}) mix(static_cast<uint32_t>(v));
    for (int i = 0; i < w.enemy_count; ++i) mix(static_cast<uint32_t>(w.enemies[i].x * 64 + w.enemies[i].y));
    for (int y = 0; y < kMapH; ++y)
        for (int x = 0; x < kMapW; ++x) mix(static_cast<unsigned char>(w.tiles[y][x]));
    return h;
}

// 0x0040205E  render
// The map with live enemies ('E') and then the player ('@') drawn on top, one puts() per row.
void render(const World& w) {
    for (int y = 0; y < kMapH; ++y) {
        char line[kMapW + 1];
        std::memcpy(line, w.tiles[y], kMapW);
        line[kMapW] = '\0';
        for (int i = 0; i < w.enemy_count; ++i)
            if (w.enemies[i].alive && w.enemies[i].y == y) line[w.enemies[i].x] = 'E';
        if (w.py == y) line[w.px] = '@';
        std::puts(line);
    }
}

}  // namespace game
