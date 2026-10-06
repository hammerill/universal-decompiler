// TinyQuest: the "original" program of universal-decompiler's worked example.
//
// A tiny deterministic game engine: it loads its assets from a packed archive (tinyquest.pak), simulates a
// maze level tick by tick (scripted player input, enemies that wander or chase), and prints a log line per
// tick plus a final hash of the world state. CI compiles it optimised and stripped; the reconstruction in
// ../reconstruction was written from that stripped binary's decompiler output and must print exactly the
// same thing. Written in the C-with-classes style of older games on purpose.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#define MAP_W 20
#define MAP_H 11
#define MAX_ENEMIES 8
#define MAX_ENTRIES 16
#define MAX_STRINGS 8
#define ASSET_CAP 4096

struct PakEntry {
    char name[24];
    uint32_t offset;
    uint32_t stored;
    uint32_t size;
    uint8_t flags;
};

struct Pak {
    PakEntry entries[MAX_ENTRIES];
    int count;
    unsigned char* blob;
    long blob_size;
};

struct Rules {
    int hp;
    int coin_score;
    int exit_bonus;
    int enemy_damage;
    int chase_radius;
};

struct Enemy {
    int x, y;
    int alive;
};

struct World {
    char tiles[MAP_H][MAP_W + 1];
    int px, py;
    int hp;
    int score;
    int coins_left;
    Enemy enemies[MAX_ENEMIES];
    int enemy_count;
    uint32_t rng;
    int finished;  // 0 running, 1 reached the exit, 2 dead, 3 out of time
    char strings[MAX_STRINGS][48];
    int string_count;
    Rules rules;
};

static uint32_t rd32(const unsigned char* p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static uint32_t rng_next(World* w) {
    w->rng = w->rng * 1103515245u + 12345u;
    return (w->rng >> 16) & 0x7fff;
}

static int read_file(const char* path, unsigned char** out, long* size) {
    FILE* f = fopen(path, "rb");
    if (!f) return 0;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    unsigned char* buf = (unsigned char*)malloc((size_t)n + 1);
    if (!buf || fread(buf, 1, (size_t)n, f) != (size_t)n) {
        fclose(f);
        free(buf);
        return 0;
    }
    fclose(f);
    buf[n] = 0;
    *out = buf;
    *size = n;
    return 1;
}

static int pak_open(Pak* pak, const char* path) {
    memset(pak, 0, sizeof(*pak));
    if (!read_file(path, &pak->blob, &pak->blob_size)) return 0;
    const unsigned char* b = pak->blob;
    if (pak->blob_size < 8 || memcmp(b, "TQPK", 4) != 0) return 0;
    int version = b[4] | (b[5] << 8);
    int count = b[6] | (b[7] << 8);
    if (version != 1 || count > MAX_ENTRIES || 8 + 40 * count > pak->blob_size) return 0;
    for (int i = 0; i < count; ++i) {
        const unsigned char* e = b + 8 + 40 * i;
        PakEntry* pe = &pak->entries[i];
        memcpy(pe->name, e, 24);
        pe->name[23] = 0;
        pe->offset = rd32(e + 24);
        pe->stored = rd32(e + 28);
        pe->size = rd32(e + 32);
        pe->flags = e[36];
    }
    pak->count = count;
    return 1;
}

static int pak_extract(const Pak* pak, const char* name, char* out, uint32_t cap) {
    for (int i = 0; i < pak->count; ++i) {
        const PakEntry* e = &pak->entries[i];
        if (strcmp(e->name, name) != 0) continue;
        if (e->offset + e->stored > (uint32_t)pak->blob_size || e->size >= cap) return -1;
        const unsigned char* src = pak->blob + e->offset;
        if (e->flags & 1) {
            uint32_t o = 0;
            for (uint32_t k = 0; k + 1 < e->stored; k += 2) {
                for (int r = 0; r < src[k] && o < e->size; ++r) out[o++] = (char)src[k + 1];
            }
        } else {
            memcpy(out, src, e->size);
        }
        out[e->size] = 0;
        return (int)e->size;
    }
    return -1;
}

static void parse_rules(Rules* r, const char* text) {
    r->hp = 3;
    r->coin_score = 1;
    r->exit_bonus = 0;
    r->enemy_damage = 1;
    r->chase_radius = 3;
    const char* p = text;
    while (*p) {
        char key[32];
        int value = 0;
        if (sscanf(p, "%31[^=]=%d", key, &value) == 2) {
            if (strcmp(key, "hp") == 0) r->hp = value;
            else if (strcmp(key, "coin_score") == 0) r->coin_score = value;
            else if (strcmp(key, "exit_bonus") == 0) r->exit_bonus = value;
            else if (strcmp(key, "enemy_damage") == 0) r->enemy_damage = value;
            else if (strcmp(key, "chase_radius") == 0) r->chase_radius = value;
        }
        while (*p && *p != '\n') ++p;
        if (*p) ++p;
    }
}

static void parse_strings(World* w, const char* text) {
    w->string_count = 0;
    const char* p = text;
    while (*p && w->string_count < MAX_STRINGS) {
        int n = 0;
        while (p[n] && p[n] != '\n') ++n;
        int c = n < 47 ? n : 47;
        memcpy(w->strings[w->string_count], p, (size_t)c);
        w->strings[w->string_count][c] = 0;
        ++w->string_count;
        p += n;
        if (*p) ++p;
    }
}

static int load_level(World* w, const char* text) {
    int x = 0, y = 0;
    w->enemy_count = 0;
    w->coins_left = 0;
    w->px = w->py = -1;
    for (const char* p = text; *p && y < MAP_H; ++p) {
        if (*p == '\n') {
            w->tiles[y][x] = 0;
            ++y;
            x = 0;
            continue;
        }
        if (x >= MAP_W) continue;
        char c = *p;
        if (c == '@') {
            w->px = x;
            w->py = y;
            c = '.';
        } else if (c == 'E' && w->enemy_count < MAX_ENEMIES) {
            Enemy* e = &w->enemies[w->enemy_count++];
            e->x = x;
            e->y = y;
            e->alive = 1;
            c = '.';
        } else if (c == '$') {
            ++w->coins_left;
        }
        w->tiles[y][x++] = c;
    }
    return w->px >= 0;
}

static int is_wall(const World* w, int x, int y) {
    if (x < 0 || y < 0 || x >= MAP_W || y >= MAP_H) return 1;
    return w->tiles[y][x] == '#';
}

static void say(const World* w, int id) {
    if (id < w->string_count) printf("  %s\n", w->strings[id]);
}

static void bite_check(World* w) {
    for (int i = 0; i < w->enemy_count; ++i) {
        const Enemy* e = &w->enemies[i];
        if (e->alive && e->x == w->px && e->y == w->py) {
            w->hp -= w->rules.enemy_damage;
            say(w, 3);
        }
    }
}

static void move_player(World* w, char cmd) {
    int dx = 0, dy = 0;
    switch (cmd) {
        case 'U': dy = -1; break;
        case 'D': dy = 1; break;
        case 'L': dx = -1; break;
        case 'R': dx = 1; break;
        default: return;
    }
    int nx = w->px + dx, ny = w->py + dy;
    if (is_wall(w, nx, ny)) {
        say(w, 1);
        return;
    }
    w->px = nx;
    w->py = ny;
    char* t = &w->tiles[ny][nx];
    if (*t == '$') {
        *t = '.';
        w->score += w->rules.coin_score;
        --w->coins_left;
        say(w, 2);
    } else if (*t == 'X') {
        w->score += w->rules.exit_bonus;
        w->finished = 1;
        say(w, 4);
    }
}

static void move_enemies(World* w) {
    static const int DX[4] = {0, 1, 0, -1};
    static const int DY[4] = {-1, 0, 1, 0};
    for (int i = 0; i < w->enemy_count; ++i) {
        Enemy* e = &w->enemies[i];
        if (!e->alive) continue;
        int ddx = w->px - e->x, ddy = w->py - e->y;
        int adx = ddx < 0 ? -ddx : ddx, ady = ddy < 0 ? -ddy : ddy;
        int nx = e->x, ny = e->y;
        if (adx + ady <= w->rules.chase_radius) {
            int sx = ddx > 0 ? 1 : (ddx < 0 ? -1 : 0);
            int sy = ddy > 0 ? 1 : (ddy < 0 ? -1 : 0);
            if (adx >= ady && sx != 0 && !is_wall(w, e->x + sx, e->y)) nx = e->x + sx;
            else if (sy != 0 && !is_wall(w, e->x, e->y + sy)) ny = e->y + sy;
            else if (sx != 0 && !is_wall(w, e->x + sx, e->y)) nx = e->x + sx;
        } else {
            uint32_t d = rng_next(w) % 4;
            nx = e->x + DX[d];
            ny = e->y + DY[d];
            if (is_wall(w, nx, ny) || w->tiles[ny][nx] == 'X') {
                nx = e->x;
                ny = e->y;
            }
        }
        e->x = nx;
        e->y = ny;
    }
}

static void tick(World* w, char cmd) {
    move_player(w, cmd);
    if (w->finished) return;
    bite_check(w);
    move_enemies(w);
    bite_check(w);
    if (w->hp <= 0) {
        w->finished = 2;
        say(w, 5);
    }
}

static uint32_t world_hash(const World* w) {
    uint32_t h = 2166136261u;
    int vals[4] = {w->px, w->py, w->hp, w->score};
    for (int i = 0; i < 4; ++i) {
        h = (h ^ (uint32_t)vals[i]) * 16777619u;
    }
    for (int i = 0; i < w->enemy_count; ++i) {
        h = (h ^ (uint32_t)(w->enemies[i].x * 64 + w->enemies[i].y)) * 16777619u;
    }
    for (int y = 0; y < MAP_H; ++y)
        for (int x = 0; x < MAP_W; ++x) h = (h ^ (unsigned char)w->tiles[y][x]) * 16777619u;
    return h;
}

static void render(const World* w) {
    for (int y = 0; y < MAP_H; ++y) {
        char line[MAP_W + 1];
        memcpy(line, w->tiles[y], MAP_W);
        line[MAP_W] = 0;
        for (int i = 0; i < w->enemy_count; ++i)
            if (w->enemies[i].alive && w->enemies[i].y == y) line[w->enemies[i].x] = 'E';
        if (w->py == y) line[w->px] = '@';
        printf("%s\n", line);
    }
}

static const char* DEMO = "UDDDDRRUUDDDDLLDDRRRRRRUULLUURRRRRLDDRRRRUUUURRDDRRRDDDDL";

int main(int argc, char** argv) {
    const char* data = "data";
    const char* inputs = DEMO;
    int ticks = 60;
    uint32_t seed = 7;
    int show = 0;
    for (int i = 1; i < argc; ++i) {
        if (strcmp(argv[i], "--data") == 0 && i + 1 < argc) data = argv[++i];
        else if (strcmp(argv[i], "--ticks") == 0 && i + 1 < argc) ticks = atoi(argv[++i]);
        else if (strcmp(argv[i], "--seed") == 0 && i + 1 < argc) seed = (uint32_t)strtoul(argv[++i], 0, 10);
        else if (strcmp(argv[i], "--inputs") == 0 && i + 1 < argc) inputs = argv[++i];
        else if (strcmp(argv[i], "--render") == 0) show = 1;
    }
    char path[512];
    snprintf(path, sizeof(path), "%s/tinyquest.pak", data);
    static Pak pak;
    if (!pak_open(&pak, path)) {
        fprintf(stderr, "cannot open %s\n", path);
        return 10;
    }
    static World w;
    static char level[ASSET_CAP], rules[ASSET_CAP], strings[ASSET_CAP];
    if (pak_extract(&pak, "level1.map", level, ASSET_CAP) < 0 || pak_extract(&pak, "rules.txt", rules, ASSET_CAP) < 0 ||
        pak_extract(&pak, "strings.txt", strings, ASSET_CAP) < 0) {
        fprintf(stderr, "damaged archive\n");
        return 11;
    }
    parse_rules(&w.rules, rules);
    parse_strings(&w, strings);
    if (!load_level(&w, level)) {
        fprintf(stderr, "bad level\n");
        return 12;
    }
    w.hp = w.rules.hp;
    w.rng = seed;
    say(&w, 0);
    int n = (int)strlen(inputs);
    for (int t = 0; t < ticks && !w.finished; ++t) {
        char cmd = n ? inputs[t % n] : '.';
        tick(&w, cmd);
        printf("t=%02d cmd=%c pos=(%d,%d) hp=%d score=%d coins_left=%d\n", t, cmd, w.px, w.py, w.hp, w.score, w.coins_left);
    }
    if (!w.finished) {
        w.finished = 3;
        say(&w, 6);
    }
    printf("result=%d score=%d hash=%08x\n", w.finished, w.score, (unsigned)world_hash(&w));
    if (show) render(&w);
    free(pak.blob);
    return w.finished == 1 ? 0 : w.finished;
}
