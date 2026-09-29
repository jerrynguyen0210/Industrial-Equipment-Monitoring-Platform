#include "gateway/sqlite/store.hpp"

#include <sqlite3.h>

#include <stdexcept>
#include <string>
#include <string_view>

namespace gateway::sqlite {
namespace {

void execute(sqlite3 *db, const char *sql) {
  const int result = sqlite3_exec(db, sql, nullptr, nullptr, nullptr);
  if (result != SQLITE_OK) {
    throw std::runtime_error("SQLite initialization failed: " + std::string(sqlite3_errmsg(db)));
  }
}

class Statement {
public:
  Statement(sqlite3 *db, const char *sql) : db_(db) {
    if (sqlite3_prepare_v2(db_, sql, -1, &statement_, nullptr) != SQLITE_OK) {
      throw std::runtime_error("SQLite statement preparation failed: " +
                               std::string(sqlite3_errmsg(db_)));
    }
  }
  ~Statement() { sqlite3_finalize(statement_); }
  Statement(const Statement &) = delete;
  Statement &operator=(const Statement &) = delete;
  sqlite3_stmt *get() const { return statement_; }

private:
  sqlite3 *db_;
  sqlite3_stmt *statement_ = nullptr;
};

void bind_text(sqlite3 *db, sqlite3_stmt *statement, int index, const std::string &value) {
  if (sqlite3_bind_text(statement, index, value.data(), static_cast<int>(value.size()),
                        SQLITE_TRANSIENT) != SQLITE_OK) {
    throw std::runtime_error("SQLite bind failed: " + std::string(sqlite3_errmsg(db)));
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
    execute(db_, "CREATE TABLE IF NOT EXISTS intake_events ("
                 "device_id TEXT NOT NULL,"
                 "boot_id TEXT NOT NULL,"
                 "sequence_number INTEGER NOT NULL CHECK (sequence_number >= 0),"
                 "mqtt_payload TEXT NOT NULL,"
                 "gateway_received_at TEXT NOT NULL,"
                 "PRIMARY KEY (device_id, boot_id, sequence_number)"
                 ") WITHOUT ROWID");
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

Store::InsertResult Store::insert(const telemetry::Event &event) {
  {
    Statement statement(
        db_, "INSERT INTO intake_events (device_id, boot_id, sequence_number, mqtt_payload, "
             "gateway_received_at) VALUES (?, ?, ?, ?, ?) "
             "ON CONFLICT(device_id, boot_id, sequence_number) DO NOTHING");
    bind_text(db_, statement.get(), 1, event.device_id);
    bind_text(db_, statement.get(), 2, event.boot_id);
    if (sqlite3_bind_int64(statement.get(), 3, event.sequence_number) != SQLITE_OK) {
      throw std::runtime_error("SQLite sequence bind failed");
    }
    bind_text(db_, statement.get(), 4, event.mqtt_payload);
    bind_text(db_, statement.get(), 5, event.gateway_received_at);
    if (sqlite3_step(statement.get()) != SQLITE_DONE) {
      throw std::runtime_error("SQLite insert failed: " + std::string(sqlite3_errmsg(db_)));
    }
  }
  if (sqlite3_changes(db_) == 1) {
    return InsertResult::inserted;
  }

  Statement statement(db_, "SELECT mqtt_payload FROM intake_events WHERE device_id=? AND "
                           "boot_id=? AND sequence_number=?");
  bind_text(db_, statement.get(), 1, event.device_id);
  bind_text(db_, statement.get(), 2, event.boot_id);
  if (sqlite3_bind_int64(statement.get(), 3, event.sequence_number) != SQLITE_OK) {
    throw std::runtime_error("SQLite sequence bind failed");
  }
  const int result = sqlite3_step(statement.get());
  if (result != SQLITE_ROW) {
    throw std::runtime_error("SQLite identity lookup failed: " + std::string(sqlite3_errmsg(db_)));
  }
  const auto *data = reinterpret_cast<const char *>(sqlite3_column_text(statement.get(), 0));
  const auto length = static_cast<std::size_t>(sqlite3_column_bytes(statement.get(), 0));
  return std::string_view(data, length) == event.mqtt_payload ? InsertResult::duplicate
                                                              : InsertResult::identity_conflict;
}

} // namespace gateway::sqlite
