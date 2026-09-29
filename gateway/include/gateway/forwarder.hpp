#pragma once

#include "gateway/sqlite/store.hpp"

#include <cstddef>
#include <vector>

namespace gateway {

// The outbound boundary can only obtain events from committed SQLite rows.
// HTTP delivery and outcome handling are separate future work.
class Forwarder {
public:
  explicit Forwarder(sqlite::Store &store);

  std::vector<sqlite::QueuedEvent>
  load_pending(std::size_t limit = sqlite::Store::max_batch_size) const;
  std::vector<sqlite::QueuedEvent> claim_pending(std::size_t limit = sqlite::Store::max_batch_size);
  bool release_claim(const sqlite::QueuedEvent &claimed);

private:
  sqlite::Store &store_;
};

} // namespace gateway
