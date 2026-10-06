// Platform layer. The original only touches the C runtime (fopen/fread for its archive, printf for its log),
// so the layer is small: reading an extracted asset and resolving data/ paths. No window, input or audio:
// the original has none, so there is no SDL backend in this reconstruction (see DECOMP_PLAN.md).
#pragma once
#include <string>
#include <vector>

namespace platform {

// <data dir>/assets/<name>: where tools/extract_assets.py puts the files it unpacks from the user's copy.
std::string asset_path(const std::string& data_dir, const std::string& name);

// Whole file, NUL-terminated (the game parses assets as C strings). False if missing or unreadable.
bool read_file(const std::string& path, std::vector<char>& out);

}  // namespace platform
