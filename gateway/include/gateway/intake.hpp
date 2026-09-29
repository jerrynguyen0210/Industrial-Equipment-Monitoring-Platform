#pragma once

#include "gateway/sqlite/store.hpp"

#include <functional>
#include <string>
#include <string_view>

namespace gateway {

class Intake {
public:
  using Clock = std::function<std::string()>;

  explicit Intake(sqlite::Store &store, Clock clock);
  void receive(std::string_view topic, std::string_view payload, bool retained);

private:
  sqlite::Store &store_;
  Clock clock_;
};

} // namespace gateway
