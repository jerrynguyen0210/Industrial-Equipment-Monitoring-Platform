#pragma once

#include <string>
#include <string_view>

namespace gateway::http {

struct Response {
  int status_code;
  std::string body;
};

// Future forwarding code owns per-item response validation before queue changes.
class Client {
public:
  virtual ~Client() = default;
  virtual Response post_batch(std::string_view body) = 0;
  virtual void stop() = 0;
};

} // namespace gateway::http
