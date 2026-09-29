#include "gateway/forwarder.hpp"

#include "gateway/log.hpp"

#include <nlohmann/json.hpp>

#include <cctype>
#include <chrono>
#include <stdexcept>
#include <string>
#include <string_view>
#include <unordered_set>
#include <utility>

namespace gateway {
namespace {

using json = nlohmann::json;

void skip_space(std::string_view source, std::size_t &position) {
  while (position < source.size() && std::isspace(static_cast<unsigned char>(source[position]))) {
    ++position;
  }
}

std::size_t quoted_end(std::string_view source, std::size_t position) {
  if (position >= source.size() || source[position] != '"') {
    throw std::runtime_error("stored event has invalid JSON member");
  }
  for (++position; position < source.size(); ++position) {
    if (source[position] == '\\') {
      ++position;
    } else if (source[position] == '"') {
      return position + 1;
    }
  }
  throw std::runtime_error("stored event has unterminated JSON string");
}

std::size_t member_end(std::string_view source, std::size_t position) {
  int depth = 0;
  while (position < source.size()) {
    const char symbol = source[position];
    if (symbol == '"') {
      position = quoted_end(source, position);
      continue;
    }
    if (symbol == '{' || symbol == '[') {
      ++depth;
    } else if (symbol == '}' || symbol == ']') {
      if (depth == 0) {
        return position;
      }
      --depth;
    } else if (symbol == ',' && depth == 0) {
      return position;
    }
    ++position;
  }
  throw std::runtime_error("stored event has incomplete JSON member");
}

// Copy raw member spans so a high precision JSON number is never rounded by a
// parse/serialize cycle. MQTT intake already validated this stored object.
std::string backend_event_json(const telemetry::Event &event) {
  const std::string_view source = event.mqtt_payload;
  std::size_t position = 0;
  skip_space(source, position);
  if (position >= source.size() || source[position++] != '{') {
    throw std::runtime_error("stored event is not a JSON object");
  }
  std::string output = "{";
  bool has_schema = false;
  bool has_member = false;
  while (true) {
    skip_space(source, position);
    if (position >= source.size()) {
      throw std::runtime_error("stored event has incomplete JSON object");
    }
    if (source[position] == '}') {
      break;
    }
    const auto start = position;
    const auto key_end = quoted_end(source, position);
    const auto key = json::parse(source.substr(position, key_end - position)).get<std::string>();
    position = key_end;
    skip_space(source, position);
    if (position >= source.size() || source[position++] != ':') {
      throw std::runtime_error("stored event has invalid JSON separator");
    }
    const auto end = member_end(source, position);
    if (key == "schema_version") {
      has_schema = true;
    } else {
      if (has_member) {
        output += ',';
      }
      output.append(source.substr(start, end - start));
      has_member = true;
    }
    position = end;
    if (source[position] == '}') {
      break;
    }
    ++position;
  }
  if (!has_schema || !has_member) {
    throw std::runtime_error("stored event is missing its schema or content");
  }
  output += ",\"gateway_received_at\":";
  output += json(event.gateway_received_at).dump();
  output += '}';
  return output;
}

std::string batch_json(const std::vector<sqlite::QueuedEvent> &claimed) {
  std::string body = "{\"schema_version\":1,\"events\":[";
  for (std::size_t index = 0; index < claimed.size(); ++index) {
    if (index != 0) {
      body += ',';
    }
    body += backend_event_json(claimed[index].event);
  }
  body += "]}";
  return body;
}

bool identity_matches(const json &item, const telemetry::Event &event, bool allow_null) {
  if (!item.contains("device_id") || !item.contains("boot_id") ||
      !item.contains("sequence_number")) {
    return false;
  }
  const auto &device = item.at("device_id");
  const auto &boot = item.at("boot_id");
  const auto &sequence = item.at("sequence_number");
  return ((allow_null && device.is_null()) || (device.is_string() && device == event.device_id)) &&
         ((allow_null && boot.is_null()) || (boot.is_string() && boot == event.boot_id)) &&
         ((allow_null && sequence.is_null()) ||
          (sequence.is_number_integer() && sequence == event.sequence_number));
}

bool permanent_reason(const std::string &reason) {
  return reason == "unknown_device" || reason == "wrong_gateway" || reason == "invalid_metric" ||
         reason == "invalid_unit" || reason == "value_out_of_range" ||
         reason == "malformed_value" || reason == "identity_conflict";
}

std::vector<sqlite::DeliveryDecision>
parse_decisions(std::string_view body, const std::vector<sqlite::QueuedEvent> &claimed) {
  std::vector<std::unordered_set<std::string>> keys;
  auto callback = [&](int depth, json::parse_event_t event, json &value) {
    if (depth < 0 || depth > 3) {
      throw std::runtime_error("batch response exceeds allowed depth");
    }
    if (event == json::parse_event_t::object_start) {
      const auto child = static_cast<std::size_t>(depth) + 1;
      if (keys.size() <= child) {
        keys.resize(child + 1);
      }
      keys[child].clear();
    } else if (event == json::parse_event_t::key) {
      if (!keys[static_cast<std::size_t>(depth)].insert(value.get<std::string>()).second) {
        throw std::runtime_error("batch response contains duplicate JSON keys");
      }
    }
    return true;
  };
  const json response = json::parse(body.begin(), body.end(), callback);
  if (!response.is_object() || response.size() != 2 || !response.contains("batch_id") ||
      !response.at("batch_id").is_string() ||
      response.at("batch_id").get_ref<const std::string &>().empty() ||
      response.at("batch_id").get_ref<const std::string &>().size() > 128 ||
      !response.contains("results") || !response.at("results").is_array() ||
      response.at("results").size() != claimed.size()) {
    throw std::runtime_error("invalid batch response envelope");
  }
  std::vector<sqlite::DeliveryDecision> decisions;
  for (std::size_t index = 0; index < claimed.size(); ++index) {
    const auto &item = response.at("results").at(index);
    if (!item.is_object() || !item.contains("outcome") || !item.at("outcome").is_string()) {
      throw std::runtime_error("invalid batch response item");
    }
    const auto outcome = item.at("outcome").get<std::string>();
    if (outcome == "accepted" || outcome == "duplicate") {
      if (item.size() != (item.contains("reason") ? 5U : 4U) ||
          !identity_matches(item, claimed[index].event, false) ||
          (item.contains("reason") && !item.at("reason").is_null())) {
        throw std::runtime_error("batch response identity mismatch");
      }
      decisions.push_back({outcome == "accepted" ? sqlite::DeliveryAction::accepted
                                                 : sqlite::DeliveryAction::duplicate,
                           {}});
    } else if (outcome == "rejected") {
      if (item.size() != 5 || !item.contains("reason") || !item.at("reason").is_string()) {
        throw std::runtime_error("batch rejection lacks a reason");
      }
      const auto reason = item.at("reason").get<std::string>();
      if (!permanent_reason(reason) ||
          !identity_matches(item, claimed[index].event, reason == "malformed_value")) {
        throw std::runtime_error("batch rejection identity mismatch");
      }
      decisions.push_back({sqlite::DeliveryAction::rejected, reason});
    } else {
      throw std::runtime_error("unknown batch outcome");
    }
  }
  return decisions;
}

} // namespace

Forwarder::Forwarder(sqlite::Store &store) : store_(store) {}
Forwarder::~Forwarder() { stop(); }

std::vector<sqlite::QueuedEvent> Forwarder::load_pending(std::size_t limit) const {
  return store_.load_pending(limit);
}

std::vector<sqlite::QueuedEvent> Forwarder::claim_pending(std::size_t limit) {
  return store_.claim_pending(limit);
}

bool Forwarder::release_claim(const sqlite::QueuedEvent &claimed) {
  return store_.release_claim(claimed);
}

Forwarder::RunResult Forwarder::drain_once(http::Client &client) {
  const auto claimed = store_.claim_pending(sqlite::Store::max_batch_size);
  if (claimed.empty()) {
    return RunResult::idle;
  }
  auto release = [&] {
    store_.apply_decisions(claimed, std::vector<sqlite::DeliveryDecision>(
                                        claimed.size(), {sqlite::DeliveryAction::retry, {}}));
  };
  std::string body;
  try {
    body = batch_json(claimed);
  } catch (const std::exception &) {
    release();
    log(Level::error, "forwarder", "delivery_deferred", "stored_event_conversion_failed");
    return RunResult::retry;
  }
  http::Response response;
  try {
    response = client.post_batch(body);
  } catch (const std::exception &) {
    release();
    log(Level::warning, "forwarder", "delivery_deferred", "http_request_failed");
    return RunResult::retry;
  }
  if (response.status_code != 200) {
    release();
    log(Level::warning, "forwarder", "delivery_deferred",
        "backend_http_status=" + std::to_string(response.status_code));
    return response.status_code == 401 || response.status_code == 403
               ? RunResult::authentication_failure
               : RunResult::retry;
  }
  std::vector<sqlite::DeliveryDecision> decisions;
  try {
    decisions = parse_decisions(response.body, claimed);
  } catch (const std::exception &) {
    release();
    log(Level::error, "forwarder", "delivery_deferred", "invalid_batch_response");
    return RunResult::retry;
  }
  try {
    store_.apply_decisions(claimed, decisions);
  } catch (const std::exception &) {
    release();
    throw;
  }
  std::size_t confirmed = 0;
  std::size_t quarantined = 0;
  for (const auto &decision : decisions) {
    if (decision.action == sqlite::DeliveryAction::rejected) {
      ++quarantined;
    } else {
      ++confirmed;
    }
  }
  log(Level::info, "forwarder", "batch_applied",
      "confirmed=" + std::to_string(confirmed) + " quarantined=" + std::to_string(quarantined));
  return RunResult::delivered;
}

void Forwarder::start(http::Client &client) {
  if (worker_.joinable()) {
    throw std::runtime_error("forwarder is already running");
  }
  client_ = &client;
  stopping_.store(false);
  worker_ = std::thread([this] {
    while (!stopping_.load()) {
      RunResult result = RunResult::retry;
      try {
        result = drain_once(*client_);
      } catch (const std::exception &) {
        log(Level::error, "forwarder", "storage_error", "queue_outcome_update_failed");
      }
      const auto delay = result == RunResult::idle                     ? std::chrono::seconds(1)
                         : result == RunResult::retry                  ? std::chrono::seconds(5)
                         : result == RunResult::authentication_failure ? std::chrono::seconds(30)
                                                                       : std::chrono::seconds(0);
      std::unique_lock<std::mutex> lock(wait_mutex_);
      wake_.wait_for(lock, delay, [&] { return stopping_.load(); });
    }
  });
}

void Forwarder::stop() {
  stopping_.store(true);
  wake_.notify_all();
  if (worker_.joinable()) {
    client_->stop();
    worker_.join();
  }
}

} // namespace gateway
