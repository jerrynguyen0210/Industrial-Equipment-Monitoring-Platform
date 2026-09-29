#pragma once

#include <filesystem>

struct sqlite3;

namespace gateway::sqlite {

class Store {
public:
  explicit Store(const std::filesystem::path &path);
  ~Store();

  Store(const Store &) = delete;
  Store &operator=(const Store &) = delete;

  void close();

private:
  sqlite3 *db_ = nullptr;
};

} // namespace gateway::sqlite
