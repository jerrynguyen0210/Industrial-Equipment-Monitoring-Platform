#pragma once

#include "gateway/config.hpp"

#include <functional>
#include <memory>
#include <string_view>

namespace gateway::mqtt {

class Client {
public:
  using OnMessage =
      std::function<void(std::string_view topic, std::string_view payload, bool retained)>;

  Client(const Config &config, OnMessage on_message);
  ~Client();
  Client(const Client &) = delete;
  Client &operator=(const Client &) = delete;

  void start();
  void stop();
  bool failed() const;

private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

} // namespace gateway::mqtt
