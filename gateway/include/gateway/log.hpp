#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <string_view>

namespace gateway {

enum class Level { info, warning, error };

struct LogContext {
  LogContext() = default;
  explicit LogContext(std::int64_t depth) : queue_depth(depth) {}
  std::optional<std::int64_t> queue_depth;
  std::optional<std::int64_t> retry_in_ms;
  std::optional<unsigned> consecutive_failures;
};

void log(Level level, std::string_view component, std::string_view event, std::string_view message,
         const LogContext &context = {});
std::string utc_now();

} // namespace gateway
