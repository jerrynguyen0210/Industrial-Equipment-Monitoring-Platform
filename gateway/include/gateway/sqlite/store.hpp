#pragma once

#include "gateway/telemetry/event.hpp"

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <mutex>
#include <string>
#include <vector>

struct sqlite3;

namespace gateway::sqlite {

enum class QueueState { pending, in_flight };

struct QueuedEvent {
  telemetry::Event event;
  QueueState state = QueueState::pending;
  std::int64_t attempt_count = 0;
};

enum class DeliveryAction { accepted, duplicate, rejected, retry };

struct DeliveryDecision {
  DeliveryAction action;
  std::string reason;
};

class Store {
public:
  enum class InsertResult { inserted, duplicate, identity_conflict };
  static constexpr std::size_t max_batch_size = 500;

  // Opens/migrates the queue and returns abandoned claims to pending.
  // One gateway process owns a database at a time.
  explicit Store(const std::filesystem::path &path);
  ~Store();

  Store(const Store &) = delete;
  Store &operator=(const Store &) = delete;

  void close();
  // Returns inserted only after the new row commits. Existing identity/content is immutable.
  InsertResult insert(const telemetry::Event &event);
  std::int64_t pending_count() const;
  std::vector<QueuedEvent> load_pending(std::size_t limit) const;
  // Atomically marks persisted rows in flight and increments their claim count.
  std::vector<QueuedEvent> claim_pending(std::size_t limit);
  bool release_claim(const QueuedEvent &claimed);
  // Applies a fully validated response in one transaction. Rejected rows move
  // to quarantine before deletion from the delivery queue.
  void apply_decisions(const std::vector<QueuedEvent> &claimed,
                       const std::vector<DeliveryDecision> &decisions);

private:
  std::vector<QueuedEvent> load_pending_unlocked(std::size_t limit) const;
  mutable std::mutex mutex_;
  sqlite3 *db_ = nullptr;
};

} // namespace gateway::sqlite
