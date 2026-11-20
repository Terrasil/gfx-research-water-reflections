#include "publication.hpp"
#include "catalog.hpp"
#include <cerrno>
#include <iostream>
#include <stdexcept>
#include <system_error>
#ifdef _WIN32
#include <process.h>
#else
#include <unistd.h>
#endif

namespace fs = std::filesystem;
namespace publication {
#ifdef _WIN32
// The Windows CRT joins spawn arguments into one command line. Preserve spaces,
// literal quotes, and runs of backslashes before a quote or the closing quote.
static std::wstring quoteArgument(const std::wstring& value) {
    if (!value.empty() && value.find_first_of(L" \t\"") == std::wstring::npos) return value;
    std::wstring result = L"\"";
    std::size_t slashes = 0;
    for (wchar_t ch : value) {
        if (ch == L'\\') {
            ++slashes;
            continue;
        }
        result.append(ch == L'\"' ? 2 * slashes + 1 : slashes, L'\\');
        result += ch;
        slashes = 0;
    }
    result.append(2 * slashes, L'\\');
    return result + L'\"';
}
#endif

int runScript(const char* filename, const std::vector<fs::path>& arguments) {
    const auto interpreter = fs::path(study::python);
    if (!fs::is_regular_file(interpreter)) {
        throw std::runtime_error("Publication Python is missing. Reload the CMake project and rebuild this executable.");
    }
    const auto script = fs::path(study::root) / "tools" / filename;
    std::vector<fs::path> words{interpreter, "-E", "-s", "-u", script};
    words.insert(words.end(), arguments.begin(), arguments.end());
#ifdef _WIN32
    std::vector<std::wstring> quoted;
    for (const auto& word : words) quoted.push_back(quoteArgument(word.native()));
    std::vector<const wchar_t*> argv;
    for (const auto& word : quoted) argv.push_back(word.c_str());
    argv.push_back(nullptr);
    const auto code = _wspawnv(_P_WAIT, interpreter.c_str(), argv.data());
    if (code != -1) return static_cast<int>(code);
#else
    std::vector<char*> argv;
    for (const auto& word : words) argv.push_back(const_cast<char*>(word.c_str()));
    argv.push_back(nullptr);
    execv(interpreter.c_str(), argv.data());
#endif
    throw std::system_error(errno, std::generic_category(), "Could not start publication Python");
}

}
