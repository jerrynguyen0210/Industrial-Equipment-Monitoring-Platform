#pragma once

#include "gateway/http/client.hpp"
#include "gateway/sqlite/store.hpp"

#include <atomic>
#include <condition_variable>
#include <cstddef>
#include <mutex>
#include <thread>
#include <vector>

namespace gateway {

class Forwarder {
public:
  enum class RunResult { idle, delivered, retry, authentication_failure };
  explicit Forwarder(sqlite::Store &store);
  ~Forwarder();
  Forwarder(const Forwarder &) = delete;
  Forwarder &operator=(const Forwarder &) = delete;

  std::vector<sqlite::QueuedEvent>
  load_pending(std::size_t limit = sqlite::Store::max_batch_size) const;
  std::vector<sqlite::QueuedEvent> claim_pending(std::size_t limit = sqlite::Store::max_batch_size);
  bool release_claim(const sqlite::QueuedEvent &claimed);
  RunResult drain_once(http::Client &client);
  // The client must outlive this worker. stop() joins before Store::close().
  void start(http::Client &client);
  void stop();

private:
  sqlite::Store &store_;
  http::Client *client_ = nullptr;
  std::atomic<bool> stopping_{false};
  std::mutex wait_mutex_;
  std::condition_variable wake_;
  std::thread worker_;
};

} // namespace gateway
