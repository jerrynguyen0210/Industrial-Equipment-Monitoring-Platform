#pragma once

#include <string>
#include <string_view>

namespace gateway {

enum class Level { info, warning, error };

void log(Level level, std::string_view component, std::string_view event, std::string_view message);
std::string utc_now();

} // namespace gateway
