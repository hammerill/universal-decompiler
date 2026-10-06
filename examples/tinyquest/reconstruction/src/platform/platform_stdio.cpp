// C stdio backend of the platform layer.
#include "platform/platform.h"

#include <cstdio>

namespace platform {

std::string asset_path(const std::string& data_dir, const std::string& name) {
    return data_dir + "/assets/" + name;
}

// Replaces 0x00401815 (read_file) + 0x00401BAC/0x00401A4E (archive open/extract): the archive is unpacked
// ahead of time by tools/extract_assets.py, so the program only reads loose files.
bool read_file(const std::string& path, std::vector<char>& out) {
    std::FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) return false;
    out.clear();
    char buf[4096];
    size_t n;
    while ((n = std::fread(buf, 1, sizeof(buf), f)) > 0) out.insert(out.end(), buf, buf + n);
    const bool ok = !std::ferror(f);
    std::fclose(f);
    out.push_back('\0');
    return ok;
}

}  // namespace platform
