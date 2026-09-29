#pragma once

#include <chrono>
#include <cstdint>
#include <random>

namespace gateway {

// Equal jitter: each delay is uniformly selected from half to all of the
// exponentially growing cap. The cap stops growing at 30 seconds.
class RetryBackoff {
public:
  explicit RetryBackoff(std::uint64_t seed = std::random_device{}());
  std::chrono::milliseconds next_delay();
  void reset();
  unsigned consecutive_failures() const;

private:
  std::mt19937_64 random_;
  std::int64_t current_cap_ms_ = 0;
  unsigned failures_ = 0;
};

} // namespace gateway
