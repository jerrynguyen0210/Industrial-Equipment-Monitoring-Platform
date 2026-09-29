#include "gateway/telemetry/event.hpp"

#include <nlohmann/json.hpp>

#include <cmath>
#include <limits>
#include <regex>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <utility>
#include <vector>

namespace gateway::telemetry {
namespace {

using json = nlohmann::json;

void require(bool condition, const char *reason) {
  if (!condition) {
    throw std::invalid_argument(reason);
  }
}

json parse_strict(std::string_view payload) {
  std::vector<std::unordered_set<std::string>> keys;
  auto callback = [&](int depth, json::parse_event_t event, json &parsed) {
    require(depth >= 0 && depth <= 4, "json_too_deep");
    if (event == json::parse_event_t::object_start) {
      const auto child_depth = static_cast<std::size_t>(depth) + 1;
      if (keys.size() <= child_depth) {
        keys.resize(child_depth + 1);
      }
      keys[child_depth].clear();
    } else if (event == json::parse_event_t::key) {
      auto &seen = keys[static_cast<std::size_t>(depth)];
      require(seen.insert(parsed.get_ref<const std::string &>()).second, "duplicate_json_key");
    }
    return true;
  };
  try {
    return json::parse(payload.begin(), payload.end(), callback);
  } catch (const json::exception &) {
    throw std::invalid_argument("invalid_json");
  }
}

template <std::size_t N>
void exact_keys(const json &object, const char *const (&expected)[N], const char *reason) {
  require(object.is_object() && object.size() == N, reason);
  for (const char *key : expected) {
    require(object.contains(key), reason);
  }
}

std::string identifier(const json &value, const char *reason) {
  require(value.is_string(), reason);
  const auto &text = value.get_ref<const std::string &>();
  require(!text.empty() && text.size() <= 128 && text.find('\0') == std::string::npos, reason);
  return text;
}

std::int64_t counter(const json &value, const char *reason) {
  if (value.is_number_unsigned()) {
    const auto number = value.get<std::uint64_t>();
    require(number <= static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max()), reason);
    return static_cast<std::int64_t>(number);
  }
  require(value.is_number_integer(), reason);
  const auto number = value.get<std::int64_t>();
  require(number >= 0, reason);
  return number;
}

bool valid_measured_at(const json &value) {
  if (value.is_null()) {
    return true;
  }
  if (!value.is_string()) {
    return false;
  }
  static const std::regex pattern(
      R"(^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})$)");
  const auto &text = value.get_ref<const std::string &>();
  if (!std::regex_match(text, pattern)) {
    return false;
  }
  const int year = std::stoi(text.substr(0, 4));
  const int month = std::stoi(text.substr(5, 2));
  const int day = std::stoi(text.substr(8, 2));
  const int hour = std::stoi(text.substr(11, 2));
  const int minute = std::stoi(text.substr(14, 2));
  const int second = std::stoi(text.substr(17, 2));
  if (year == 0 || month < 1 || month > 12 || hour > 23 || minute > 59 || second > 59) {
    return false;
  }
  constexpr int days_in_month[] = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
  const bool leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
  const int days = days_in_month[month - 1] + (month == 2 && leap ? 1 : 0);
  if (day < 1 || day > days) {
    return false;
  }
  const auto offset = text.find_last_of("+-");
  if (offset != std::string::npos && offset >= 19) {
    return std::stoi(text.substr(offset + 1, 2)) <= 23 &&
           std::stoi(text.substr(offset + 4, 2)) <= 59;
  }
  return true;
}

std::string topic_device_id(std::string_view topic) {
  constexpr std::string_view prefix = "equipment/";
  constexpr std::string_view suffix = "/telemetry";
  require(topic.size() > prefix.size() + suffix.size() &&
              topic.substr(0, prefix.size()) == prefix &&
              topic.substr(topic.size() - suffix.size()) == suffix,
          "invalid_topic");
  const auto device = topic.substr(prefix.size(), topic.size() - prefix.size() - suffix.size());
  require(device.size() <= 128 && device.find_first_of("/+#") == std::string_view::npos,
          "invalid_topic");
  return std::string(device);
}

} // namespace

Event parse(std::string_view topic, std::string_view payload, std::string gateway_received_at) {
  require(payload.size() <= max_payload_bytes, "payload_too_large");
  const auto device_from_topic = topic_device_id(topic);
  const json data = parse_strict(payload);
  require(!data.is_object() || !data.contains("gateway_received_at"),
          "gateway_received_at_forbidden");
  constexpr const char *fields[] = {"schema_version",  "device_id",   "boot_id",
                                    "sequence_number", "measured_at", "device_uptime_ms",
                                    "metric",          "value",       "unit",
                                    "quality"};
  exact_keys(data, fields, "invalid_event_fields");
  require((data.at("schema_version").is_number_integer() ||
           data.at("schema_version").is_number_unsigned()) &&
              data.at("schema_version") == 1,
          "unsupported_schema_version");
  Event event;
  event.device_id = identifier(data.at("device_id"), "invalid_device_id");
  require(event.device_id == device_from_topic, "topic_device_mismatch");
  event.boot_id = identifier(data.at("boot_id"), "invalid_boot_id");
  event.sequence_number = counter(data.at("sequence_number"), "invalid_sequence_number");
  counter(data.at("device_uptime_ms"), "invalid_device_uptime_ms");
  require(valid_measured_at(data.at("measured_at")), "invalid_measured_at");
  require(data.at("metric").is_string() && data.at("metric") == "temperature", "invalid_metric");
  require(data.at("unit").is_string() && data.at("unit") == "celsius", "invalid_unit");
  require(data.at("value").is_number() && std::isfinite(data.at("value").get<double>()),
          "invalid_value");
  constexpr const char *quality_fields[] = {"reading", "clock"};
  const json &quality = data.at("quality");
  exact_keys(quality, quality_fields, "invalid_quality");
  require(quality.at("reading").is_string() && quality.at("reading") == "valid", "invalid_quality");
  const json &clock = quality.at("clock");
  require(clock.is_string() && (clock == "synchronised" || clock == "unsynchronised" ||
                                clock == "estimated" || clock == "unknown"),
          "invalid_quality");
  event.mqtt_payload = std::string(payload);
  event.gateway_received_at = std::move(gateway_received_at);
  return event;
}

} // namespace gateway::telemetry
