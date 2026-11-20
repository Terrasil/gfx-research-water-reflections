#pragma once
#include <filesystem>
#include <vector>

namespace publication {
int runScript(const char* filename, const std::vector<std::filesystem::path>& arguments);
}
