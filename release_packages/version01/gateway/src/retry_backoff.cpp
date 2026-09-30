#include "gateway/retry_backoff.hpp"

#include <algorithm>
#include <limits>

namespace gateway {

namespace {
constexpr std::int64_t initial_cap_ms = 2000;
constexpr std::int64_t max_cap_ms = 30000;
} // namespace

RetryBackoff::RetryBackoff(std::uint64_t seed) : random_(seed) {}

std::chrono::milliseconds RetryBackoff::next_delay() {
  current_cap_ms_ =
      current_cap_ms_ == 0 ? initial_cap_ms : std::min(current_cap_ms_ * 2, max_cap_ms);
  if (failures_ < std::numeric_limits<unsigned>::max()) {
    ++failures_;
  }
  std::uniform_int_distribution<std::int64_t> distribution(current_cap_ms_ / 2, current_cap_ms_);
  return std::chrono::milliseconds(distribution(random_));
}

void RetryBackoff::reset() {
  current_cap_ms_ = 0;
  failures_ = 0;
}

unsigned RetryBackoff::consecutive_failures() const { return failures_; }

} // namespace gateway
