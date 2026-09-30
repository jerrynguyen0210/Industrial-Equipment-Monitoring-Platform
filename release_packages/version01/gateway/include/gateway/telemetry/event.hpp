#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>

namespace gateway::telemetry {

constexpr std::size_t max_payload_bytes = 16384;

struct Event {
  std::string device_id;
  std::string boot_id;
  std::int64_t sequence_number = 0;
  std::string mqtt_payload;
  std::string gateway_received_at;
};

// Raises std::invalid_argument with a safe reason; never echoes payload values.
Event parse(std::string_view topic, std::string_view payload, std::string gateway_received_at);

} // namespace gateway::telemetry
