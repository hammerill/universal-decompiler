// TinyQuest reconstruction: entry point.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>
#include <string>
#include <utility>
#include <vector>

#include "game/world.h"
#include "platform/platform.h"

namespace {

// The built-in demo input, a string constant referenced from main in the original.
constexpr const char* kDemoInputs = "UDDDDRRUUDDDDLLDDRRRRRRUULLUURRRRRLDDRRRRUUUURRDDRRRDDDDL";

struct Options {
    std::string data = "data";
    std::string inputs = kDemoInputs;
    int ticks = 60;
    uint32_t seed = 7;
    bool render = false;
};

Options parse_args(int argc, char** argv) {
    Options o;
    for (int i = 1; i < argc; ++i) {
        const bool has_value = i + 1 < argc;
        if (std::strcmp(argv[i], "--data") == 0 && has_value) o.data = argv[++i];
        else if (std::strcmp(argv[i], "--ticks") == 0 && has_value) o.ticks = std::atoi(argv[++i]);
        else if (std::strcmp(argv[i], "--seed") == 0 && has_value) o.seed = static_cast<uint32_t>(std::strtoul(argv[++i], nullptr, 10));
        else if (std::strcmp(argv[i], "--inputs") == 0 && has_value) o.inputs = argv[++i];
        else if (std::strcmp(argv[i], "--render") == 0) o.render = true;
    }
    return o;
}

}  // namespace

// 0x00402122  main
// Exit codes as in the original: 0 = reached the exit, 2 = dead, 3 = out of time; 10/11/12 = missing,
// damaged or invalid assets (the original reports archive errors there; see the README's known gaps).
int main(int argc, char** argv) {
    const Options opt = parse_args(argc, argv);

    std::vector<char> level, rules, strings;
    for (auto [name, buf] : {std::pair<const char*, std::vector<char>*>{"level1.map", &level}, {"rules.txt", &rules}, {"strings.txt", &strings}}) {
        const std::string path = platform::asset_path(opt.data, name);
        if (!platform::read_file(path, *buf)) {
            std::fprintf(stderr, "cannot open %s (run: uv run tools/extract_assets.py <your copy>)\n", path.c_str());
            return 10;
        }
    }

    static game::World w;   // a single global in the original (0x004080E0)
    game::parse_rules(w.rules, rules.data());
    game::parse_strings(w, strings.data());
    if (!game::load_level(w, level.data())) {
        std::fprintf(stderr, "bad level\n");
        return 12;
    }
    w.hp = w.rules.hp;
    w.rng = opt.seed;
    game::say(w, game::kTitle);

    const int n = static_cast<int>(opt.inputs.size());
    for (int t = 0; t < opt.ticks && w.outcome == game::Outcome::Running; ++t) {
        const char cmd = n ? opt.inputs[static_cast<size_t>(t % n)] : '.';
        game::tick(w, cmd);
        std::printf("t=%02d cmd=%c pos=(%d,%d) hp=%d score=%d coins_left=%d\n", t, cmd, w.px, w.py, w.hp, w.score, w.coins_left);
    }
    if (w.outcome == game::Outcome::Running) {
        w.outcome = game::Outcome::OutOfTime;
        game::say(w, game::kOutOfTime);
    }
    const int outcome = static_cast<int>(w.outcome);
    std::printf("result=%d score=%d hash=%08x\n", outcome, w.score, static_cast<unsigned>(game::world_hash(w)));
    if (opt.render) game::render(w);
    return w.outcome == game::Outcome::Exit ? 0 : outcome;
}
