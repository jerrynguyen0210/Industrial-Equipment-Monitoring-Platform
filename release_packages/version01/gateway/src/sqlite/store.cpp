#include "gateway/sqlite/store.hpp"

#include <sqlite3.h>

#include <limits>
#include <map>
#include <mutex>
#include <stdexcept>
#include <string>
#include <vector>

namespace gateway::sqlite {
namespace {

void execute(sqlite3 *db, const char *sql) {
  const int result = sqlite3_exec(db, sql, nullptr, nullptr, nullptr);
  if (result != SQLITE_OK) {
    throw std::runtime_error("SQLite operation failed: " + std::string(sqlite3_errmsg(db)));
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

class Transaction {
public:
  explicit Transaction(sqlite3 *db) : db_(db) { execute(db_, "BEGIN IMMEDIATE"); }
  ~Transaction() {
    if (active_) {
      sqlite3_exec(db_, "ROLLBACK", nullptr, nullptr, nullptr);
    }
  }
  Transaction(const Transaction &) = delete;
  Transaction &operator=(const Transaction &) = delete;
  void commit() {
    execute(db_, "COMMIT");
    active_ = false;
  }

private:
  sqlite3 *db_;
  bool active_ = true;
};

std::string column_text(sqlite3_stmt *statement, int index) {
  const auto *data = reinterpret_cast<const char *>(sqlite3_column_text(statement, index));
  if (!data) {
    throw std::runtime_error("SQLite queue row contains a null text field");
  }
  const auto length = static_cast<std::size_t>(sqlite3_column_bytes(statement, index));
  return std::string(data, length);
}

std::map<std::string, int> table_columns(sqlite3 *db) {
  Statement statement(db, "PRAGMA table_info(intake_events)");
  std::map<std::string, int> columns;
  int result = SQLITE_ROW;
  while ((result = sqlite3_step(statement.get())) == SQLITE_ROW) {
    columns.emplace(column_text(statement.get(), 1), sqlite3_column_int(statement.get(), 5));
  }
  if (result != SQLITE_DONE) {
    throw std::runtime_error("cannot inspect SQLite queue schema");
  }
  return columns;
}

void initialize_schema(sqlite3 *db) {
  Transaction transaction(db);
  {
    Statement version_statement(db, "PRAGMA user_version");
    if (sqlite3_step(version_statement.get()) != SQLITE_ROW) {
      throw std::runtime_error("cannot read SQLite queue schema version");
    }
    const int version = sqlite3_column_int(version_statement.get(), 0);
    if (version < 0 || version > 2) {
      throw std::runtime_error("unsupported SQLite queue schema version");
    }
  }

  execute(db, "CREATE TABLE IF NOT EXISTS intake_events ("
              "device_id TEXT NOT NULL,"
              "boot_id TEXT NOT NULL,"
              "sequence_number INTEGER NOT NULL CHECK (sequence_number >= 0),"
              "mqtt_payload TEXT NOT NULL,"
              "gateway_received_at TEXT NOT NULL,"
              "queue_state TEXT NOT NULL DEFAULT 'pending' "
              "CHECK (queue_state IN ('pending', 'in_flight')),"
              "attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),"
              "PRIMARY KEY (device_id, boot_id, sequence_number)"
              ") WITHOUT ROWID");

  const auto columns = table_columns(db);
  if (columns.count("device_id") == 0 || columns.at("device_id") != 1 ||
      columns.count("boot_id") == 0 || columns.at("boot_id") != 2 ||
      columns.count("sequence_number") == 0 || columns.at("sequence_number") != 3 ||
      columns.count("mqtt_payload") == 0 || columns.count("gateway_received_at") == 0) {
    throw std::runtime_error("unsupported existing SQLite queue schema");
  }
  if (columns.count("queue_state") == 0) {
    execute(db, "ALTER TABLE intake_events ADD COLUMN queue_state TEXT NOT NULL "
                "DEFAULT 'pending' CHECK (queue_state IN ('pending', 'in_flight'))");
  }
  if (columns.count("attempt_count") == 0) {
    execute(db, "ALTER TABLE intake_events ADD COLUMN attempt_count INTEGER NOT NULL "
                "DEFAULT 0 CHECK (attempt_count >= 0)");
  }
  execute(db, "CREATE INDEX IF NOT EXISTS intake_events_pending_order "
              "ON intake_events(queue_state, gateway_received_at, device_id, boot_id, "
              "sequence_number)");
  execute(db, "CREATE TABLE IF NOT EXISTS quarantined_events ("
              "device_id TEXT NOT NULL, boot_id TEXT NOT NULL, "
              "sequence_number INTEGER NOT NULL, mqtt_payload TEXT NOT NULL, "
              "gateway_received_at TEXT NOT NULL, attempt_count INTEGER NOT NULL, "
              "reason TEXT NOT NULL, quarantined_at TEXT NOT NULL, "
              "PRIMARY KEY (device_id, boot_id, sequence_number)) WITHOUT ROWID");
  {
    Statement invalid(db, "SELECT COUNT(*) FROM intake_events WHERE queue_state IS NULL OR "
                          "queue_state NOT IN ('pending', 'in_flight') OR attempt_count IS NULL "
                          "OR attempt_count < 0");
    if (sqlite3_step(invalid.get()) != SQLITE_ROW || sqlite3_column_int64(invalid.get(), 0) != 0) {
      throw std::runtime_error("SQLite queue contains invalid state or attempt count");
    }
  }
  execute(db, "UPDATE intake_events SET queue_state='pending' "
              "WHERE queue_state='in_flight'");
  execute(db, "PRAGMA user_version=2");
  transaction.commit();
}

QueuedEvent read_row(sqlite3_stmt *statement) {
  QueuedEvent row;
  row.event.device_id = column_text(statement, 0);
  row.event.boot_id = column_text(statement, 1);
  row.event.sequence_number = sqlite3_column_int64(statement, 2);
  row.event.mqtt_payload = column_text(statement, 3);
  row.event.gateway_received_at = column_text(statement, 4);
  const auto state = column_text(statement, 5);
  if (state == "pending") {
    row.state = QueueState::pending;
  } else if (state == "in_flight") {
    row.state = QueueState::in_flight;
  } else {
    throw std::runtime_error("SQLite queue contains an unknown state");
  }
  row.attempt_count = sqlite3_column_int64(statement, 6);
  if (row.attempt_count < 0) {
    throw std::runtime_error("SQLite queue contains a negative attempt count");
  }
  return row;
}

void validate_limit(std::size_t limit) {
  if (limit == 0 || limit > Store::max_batch_size) {
    throw std::invalid_argument("SQLite queue batch limit must be between 1 and 500");
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
    initialize_schema(db_);
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
  const std::lock_guard<std::mutex> lock(mutex_);
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
  const std::lock_guard<std::mutex> lock(mutex_);
  Transaction transaction(db_);
  {
    Statement quarantined(db_, "SELECT mqtt_payload FROM quarantined_events WHERE device_id=? "
                               "AND boot_id=? AND sequence_number=?");
    bind_text(db_, quarantined.get(), 1, event.device_id);
    bind_text(db_, quarantined.get(), 2, event.boot_id);
    if (sqlite3_bind_int64(quarantined.get(), 3, event.sequence_number) != SQLITE_OK) {
      throw std::runtime_error("SQLite quarantine identity bind failed");
    }
    const int result = sqlite3_step(quarantined.get());
    if (result == SQLITE_ROW) {
      return column_text(quarantined.get(), 0) == event.mqtt_payload
                 ? InsertResult::duplicate
                 : InsertResult::identity_conflict;
    }
    if (result != SQLITE_DONE) {
      throw std::runtime_error("SQLite quarantine identity lookup failed");
    }
  }
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
    transaction.commit();
    return InsertResult::inserted;
  }

  bool duplicate = false;
  {
    Statement statement(db_, "SELECT mqtt_payload FROM intake_events WHERE device_id=? AND "
                             "boot_id=? AND sequence_number=?");
    bind_text(db_, statement.get(), 1, event.device_id);
    bind_text(db_, statement.get(), 2, event.boot_id);
    if (sqlite3_bind_int64(statement.get(), 3, event.sequence_number) != SQLITE_OK) {
      throw std::runtime_error("SQLite sequence bind failed");
    }
    const int result = sqlite3_step(statement.get());
    if (result != SQLITE_ROW) {
      throw std::runtime_error("SQLite identity lookup failed: " +
                               std::string(sqlite3_errmsg(db_)));
    }
    duplicate = column_text(statement.get(), 0) == event.mqtt_payload;
  }
  transaction.commit();
  return duplicate ? InsertResult::duplicate : InsertResult::identity_conflict;
}

std::int64_t Store::queue_depth() const {
  const std::lock_guard<std::mutex> lock(mutex_);
  Statement statement(db_, "SELECT COUNT(*) FROM intake_events");
  if (sqlite3_step(statement.get()) != SQLITE_ROW) {
    throw std::runtime_error("cannot count SQLite queue rows");
  }
  return sqlite3_column_int64(statement.get(), 0);
}

std::int64_t Store::pending_count() const {
  const std::lock_guard<std::mutex> lock(mutex_);
  Statement statement(db_, "SELECT COUNT(*) FROM intake_events WHERE queue_state='pending'");
  if (sqlite3_step(statement.get()) != SQLITE_ROW) {
    throw std::runtime_error("cannot count pending SQLite queue rows");
  }
  return sqlite3_column_int64(statement.get(), 0);
}

std::vector<QueuedEvent> Store::load_pending(std::size_t limit) const {
  const std::lock_guard<std::mutex> lock(mutex_);
  return load_pending_unlocked(limit);
}

std::vector<QueuedEvent> Store::load_pending_unlocked(std::size_t limit) const {
  validate_limit(limit);
  Statement statement(db_, "SELECT device_id, boot_id, sequence_number, mqtt_payload, "
                           "gateway_received_at, queue_state, attempt_count "
                           "FROM intake_events WHERE queue_state='pending' "
                           "ORDER BY gateway_received_at, device_id, boot_id, sequence_number "
                           "LIMIT ?");
  if (sqlite3_bind_int64(statement.get(), 1, static_cast<sqlite3_int64>(limit)) != SQLITE_OK) {
    throw std::runtime_error("cannot bind SQLite queue batch limit");
  }
  std::vector<QueuedEvent> rows;
  int result = SQLITE_ROW;
  while ((result = sqlite3_step(statement.get())) == SQLITE_ROW) {
    rows.push_back(read_row(statement.get()));
  }
  if (result != SQLITE_DONE) {
    throw std::runtime_error("cannot load pending SQLite queue rows: " +
                             std::string(sqlite3_errmsg(db_)));
  }
  return rows;
}

std::vector<QueuedEvent> Store::claim_pending(std::size_t limit) {
  const std::lock_guard<std::mutex> lock(mutex_);
  Transaction transaction(db_);
  auto rows = load_pending_unlocked(limit);
  for (auto &row : rows) {
    if (row.attempt_count == std::numeric_limits<std::int64_t>::max()) {
      throw std::runtime_error("SQLite queue attempt count overflow");
    }
    Statement statement(db_, "UPDATE intake_events SET queue_state='in_flight', "
                             "attempt_count=attempt_count+1 WHERE device_id=? AND boot_id=? "
                             "AND sequence_number=? AND queue_state='pending' AND attempt_count=?");
    bind_text(db_, statement.get(), 1, row.event.device_id);
    bind_text(db_, statement.get(), 2, row.event.boot_id);
    if (sqlite3_bind_int64(statement.get(), 3, row.event.sequence_number) != SQLITE_OK ||
        sqlite3_bind_int64(statement.get(), 4, row.attempt_count) != SQLITE_OK) {
      throw std::runtime_error("cannot bind SQLite queue claim identity");
    }
    if (sqlite3_step(statement.get()) != SQLITE_DONE || sqlite3_changes(db_) != 1) {
      throw std::runtime_error("cannot claim pending SQLite queue row");
    }
    row.state = QueueState::in_flight;
    ++row.attempt_count;
  }
  transaction.commit();
  return rows;
}

bool Store::release_claim(const QueuedEvent &claimed) {
  if (claimed.state != QueueState::in_flight) {
    throw std::invalid_argument("only an in-flight SQLite queue row can be released");
  }
  const std::lock_guard<std::mutex> lock(mutex_);
  Transaction transaction(db_);
  bool released = false;
  {
    Statement statement(db_, "UPDATE intake_events SET queue_state='pending' "
                             "WHERE device_id=? AND boot_id=? AND sequence_number=? "
                             "AND queue_state='in_flight' AND attempt_count=?");
    bind_text(db_, statement.get(), 1, claimed.event.device_id);
    bind_text(db_, statement.get(), 2, claimed.event.boot_id);
    if (sqlite3_bind_int64(statement.get(), 3, claimed.event.sequence_number) != SQLITE_OK ||
        sqlite3_bind_int64(statement.get(), 4, claimed.attempt_count) != SQLITE_OK) {
      throw std::runtime_error("cannot bind SQLite queue release identity");
    }
    if (sqlite3_step(statement.get()) != SQLITE_DONE) {
      throw std::runtime_error("cannot release SQLite queue row: " +
                               std::string(sqlite3_errmsg(db_)));
    }
    released = sqlite3_changes(db_) == 1;
  }
  transaction.commit();
  return released;
}

void Store::apply_decisions(const std::vector<QueuedEvent> &claimed,
                            const std::vector<DeliveryDecision> &decisions) {
  if (claimed.size() != decisions.size() || claimed.empty() || claimed.size() > max_batch_size) {
    throw std::invalid_argument("delivery decisions must match a nonempty claimed batch");
  }
  const std::lock_guard<std::mutex> lock(mutex_);
  Transaction transaction(db_);
  for (std::size_t index = 0; index < claimed.size(); ++index) {
    const auto &row = claimed[index];
    const auto &decision = decisions[index];
    if (row.state != QueueState::in_flight || row.attempt_count <= 0) {
      throw std::invalid_argument("delivery decision requires an in-flight claim");
    }
    if (decision.action != DeliveryAction::accepted &&
        decision.action != DeliveryAction::duplicate &&
        decision.action != DeliveryAction::rejected && decision.action != DeliveryAction::retry) {
      throw std::invalid_argument("unknown delivery action");
    }
    if (decision.action == DeliveryAction::rejected) {
      if (decision.reason.empty()) {
        throw std::invalid_argument("rejected delivery requires a reason");
      }
      Statement quarantine(db_,
                           "INSERT INTO quarantined_events "
                           "(device_id, boot_id, sequence_number, mqtt_payload, "
                           "gateway_received_at, attempt_count, reason, quarantined_at) "
                           "VALUES (?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))");
      bind_text(db_, quarantine.get(), 1, row.event.device_id);
      bind_text(db_, quarantine.get(), 2, row.event.boot_id);
      if (sqlite3_bind_int64(quarantine.get(), 3, row.event.sequence_number) != SQLITE_OK ||
          sqlite3_bind_int64(quarantine.get(), 6, row.attempt_count) != SQLITE_OK) {
        throw std::runtime_error("cannot bind quarantine identity");
      }
      bind_text(db_, quarantine.get(), 4, row.event.mqtt_payload);
      bind_text(db_, quarantine.get(), 5, row.event.gateway_received_at);
      bind_text(db_, quarantine.get(), 7, decision.reason);
      if (sqlite3_step(quarantine.get()) != SQLITE_DONE) {
        throw std::runtime_error("cannot quarantine event: " + std::string(sqlite3_errmsg(db_)));
      }
    } else if (!decision.reason.empty()) {
      throw std::invalid_argument("non-rejected delivery cannot have a reason");
    }

    const char *sql = decision.action == DeliveryAction::retry
                          ? "UPDATE intake_events SET queue_state='pending' WHERE device_id=? "
                            "AND boot_id=? AND sequence_number=? AND queue_state='in_flight' "
                            "AND attempt_count=?"
                          : "DELETE FROM intake_events WHERE device_id=? AND boot_id=? "
                            "AND sequence_number=? AND queue_state='in_flight' AND attempt_count=?";
    Statement update(db_, sql);
    bind_text(db_, update.get(), 1, row.event.device_id);
    bind_text(db_, update.get(), 2, row.event.boot_id);
    if (sqlite3_bind_int64(update.get(), 3, row.event.sequence_number) != SQLITE_OK ||
        sqlite3_bind_int64(update.get(), 4, row.attempt_count) != SQLITE_OK) {
      throw std::runtime_error("cannot bind delivery claim");
    }
    if (sqlite3_step(update.get()) != SQLITE_DONE || sqlite3_changes(db_) != 1) {
      throw std::runtime_error("delivery claim changed before outcome was applied");
    }
  }
  transaction.commit();
}

} // namespace gateway::sqlite
