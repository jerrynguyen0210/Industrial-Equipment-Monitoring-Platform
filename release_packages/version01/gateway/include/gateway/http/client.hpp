#pragma once

#include <atomic>
#include <string>
#include <string_view>

namespace gateway::http {

struct Response {
  int status_code;
  std::string body;
};

class Client {
public:
  virtual ~Client() = default;
  virtual Response post_batch(std::string_view body) = 0;
  virtual void stop() = 0;
};

class CurlClient final : public Client {
public:
  CurlClient(std::string api_base_url, std::string gateway_api_key);
  ~CurlClient() override;
  CurlClient(const CurlClient &) = delete;
  CurlClient &operator=(const CurlClient &) = delete;

  Response post_batch(std::string_view body) override;
  void stop() override;

private:
  std::string url_;
  std::string token_;
  std::atomic<bool> stopping_{false};
};

} // namespace gateway::http
