#include "gateway/intake.hpp"

#include "gateway/log.hpp"
#include "gateway/telemetry/event.hpp"

#include <stdexcept>
#include <string>
#include <utility>

namespace gateway {

Intake::Intake(sqlite::Store &store, Clock clock) : store_(store), clock_(std::move(clock)) {}

void Intake::receive(std::string_view topic, std::string_view payload, bool retained) {
  const std::string received_at = clock_();
  if (retained) {
    log(Level::warning, "intake", "message_rejected", "retained_message");
    return;
  }

  telemetry::Event event;
  try {
    event = telemetry::parse(topic, payload, received_at);
  } catch (const std::invalid_argument &error) {
    log(Level::warning, "intake", "message_rejected", error.what());
    return;
  }

  const auto result = store_.insert(event);
  const std::string identity = "device_id=" + event.device_id + " boot_id=" + event.boot_id +
                               " sequence_number=" + std::to_string(event.sequence_number);
  switch (result) {
  case sqlite::Store::InsertResult::inserted:
    log(Level::info, "intake", "message_stored", identity);
    break;
  case sqlite::Store::InsertResult::duplicate:
    log(Level::info, "intake", "message_duplicate", identity);
    break;
  case sqlite::Store::InsertResult::identity_conflict:
    log(Level::warning, "intake", "identity_conflict", identity);
    break;
  }
}

} // namespace gateway
