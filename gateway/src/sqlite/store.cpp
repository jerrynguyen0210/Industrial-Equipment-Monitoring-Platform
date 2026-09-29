#include "gateway/sqlite/store.hpp"

#include <sqlite3.h>

#include <stdexcept>
#include <string>

namespace gateway::sqlite {
namespace {

void execute(sqlite3 *db, const char *sql) {
  const int result = sqlite3_exec(db, sql, nullptr, nullptr, nullptr);
  if (result != SQLITE_OK) {
    throw std::runtime_error("SQLite initialization failed: " + std::string(sqlite3_errmsg(db)));
  }
}

} // namespace

Store::Store(const std::filesystem::path &path) {
  const int result =
      sqlite3_open_v2(path.string().c_str(), &db_,
                      SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE | SQLITE_OPEN_FULLMUTEX, nullptr);
  if (result != SQLITE_OK) {
    const std::string detail = db_ ? sqlite3_errmsg(db_) : sqlite3_errstr(result);
    if (db_) {
      sqlite3_close_v2(db_);
      db_ = nullptr;
    }
    throw std::runtime_error("cannot open SQLite database: " + detail);
  }

  try {
    if (sqlite3_busy_timeout(db_, 5000) != SQLITE_OK) {
      throw std::runtime_error("cannot set SQLite busy timeout");
    }
    sqlite3_stmt *statement = nullptr;
    if (sqlite3_prepare_v2(db_, "PRAGMA journal_mode=WAL", -1, &statement, nullptr) != SQLITE_OK) {
      throw std::runtime_error("cannot enable SQLite WAL mode: " +
                               std::string(sqlite3_errmsg(db_)));
    }
    const int step = sqlite3_step(statement);
    const unsigned char *mode = step == SQLITE_ROW ? sqlite3_column_text(statement, 0) : nullptr;
    const bool wal = mode && std::string(reinterpret_cast<const char *>(mode)) == "wal";
    sqlite3_finalize(statement);
    if (!wal) {
      throw std::runtime_error("SQLite database does not support WAL mode");
    }
    execute(db_, "PRAGMA synchronous=FULL");
    execute(db_, "PRAGMA foreign_keys=ON");
  } catch (...) {
    sqlite3_close_v2(db_);
    db_ = nullptr;
    throw;
  }
}

Store::~Store() {
  if (db_) {
    sqlite3_close_v2(db_);
  }
}

void Store::close() {
  if (!db_) {
    return;
  }
  const int result = sqlite3_close(db_);
  if (result != SQLITE_OK) {
    throw std::runtime_error("cannot close SQLite database: " +
                             std::string(sqlite3_errstr(result)));
  }
  db_ = nullptr;
}

} // namespace gateway::sqlite
