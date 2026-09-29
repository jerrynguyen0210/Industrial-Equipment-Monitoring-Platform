#pragma once

#include <string_view>

namespace gateway {

enum class Level { info, warning, error };

void log(Level level, std::string_view component, std::string_view event, std::string_view message);

} // namespace gateway
