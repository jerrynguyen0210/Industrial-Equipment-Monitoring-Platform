#pragma once

#include "gateway/telemetry/event.hpp"

#include <filesystem>

struct sqlite3;

namespace gateway::sqlite {

class Store {
public:
  enum class InsertResult { inserted, duplicate, identity_conflict };

  explicit Store(const std::filesystem::path &path);
  ~Store();

  Store(const Store &) = delete;
  Store &operator=(const Store &) = delete;

  void close();
  InsertResult insert(const telemetry::Event &event);

private:
  sqlite3 *db_ = nullptr;
};

} // namespace gateway::sqlite
