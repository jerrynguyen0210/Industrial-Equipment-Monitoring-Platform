#pragma once

#include <functional>
#include <string>
#include <string_view>

namespace gateway::mqtt {

struct Message {
  std::string topic;
  std::string payload;
  bool retained = false;
};

// Future MQTT adapters deliver messages through this boundary. The service does
// not instantiate one until authenticated intake and durable persistence exist.
class Client {
public:
  virtual ~Client() = default;
  virtual void subscribe(std::string_view topic,
                         std::function<void(const Message &)> on_message) = 0;
  virtual void stop() = 0;
};

} // namespace gateway::mqtt
