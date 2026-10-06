// Shared by the backends (included, not compiled on its own).
#include <cstdarg>
#include <cstdio>
#include <cstdlib>

namespace platform {

std::string data_path(const std::string& relative) {
    const char* env = std::getenv("UD_DATA_DIR");
    std::string base = env && *env ? env : "data";
    if (!base.empty() && base.back() != '/' && base.back() != '\\') base += '/';
    return base + relative;
}

void log(const char* fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    std::vfprintf(stderr, fmt, ap);
    va_end(ap);
    std::fputc('\n', stderr);
    std::fflush(stderr);
}

}  // namespace platform
