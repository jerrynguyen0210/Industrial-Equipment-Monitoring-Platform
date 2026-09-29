#include "gateway/forwarder.hpp"

namespace gateway {

Forwarder::Forwarder(sqlite::Store &store) : store_(store) {}

std::vector<sqlite::QueuedEvent> Forwarder::load_pending(std::size_t limit) const {
  return store_.load_pending(limit);
}

std::vector<sqlite::QueuedEvent> Forwarder::claim_pending(std::size_t limit) {
  return store_.claim_pending(limit);
}

bool Forwarder::release_claim(const sqlite::QueuedEvent &claimed) {
  return store_.release_claim(claimed);
}

} // namespace gateway
