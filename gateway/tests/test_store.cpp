#include "gateway/forwarder.hpp"
#include "gateway/sqlite/store.hpp"

#include <sqlite3.h>

#include <cstdlib>
#include <filesystem>
#include <stdexcept>
#include <string>
#include <system_error>
#include <vector>

namespace {

void expect(bool condition, const char *message) {
  if (!condition) {
    throw std::runtime_error(message);
  }
}

class TemporaryDirectory {
public:
  TemporaryDirectory() {
    std::string pattern =
        (std::filesystem::temp_directory_path() / "gateway-store-XXXXXX").string();
    std::vector<char> buffer(pattern.begin(), pattern.end());
    buffer.push_back('\0');
    char *created = mkdtemp(buffer.data());
    if (!created) {
      throw std::runtime_error("cannot create test directory");
    }
    path = created;
  }
  ~TemporaryDirectory() {
    std::error_code ignored;
    std::filesystem::remove_all(path, ignored);
  }

  std::filesystem::path path;
};

class RawDatabase {
public:
  explicit RawDatabase(const std::filesystem::path &path) {
    if (sqlite3_open(path.string().c_str(), &db_) != SQLITE_OK) {
      sqlite3_close(db_);
      db_ = nullptr;
      throw std::runtime_error("cannot open raw test database");
    }
  }
  ~RawDatabase() { sqlite3_close(db_); }
  void execute(const char *sql) {
    if (sqlite3_exec(db_, sql, nullptr, nullptr, nullptr) != SQLITE_OK) {
      throw std::runtime_error(sqlite3_errmsg(db_));
    }
  }
  int scalar(const char *sql) {
    sqlite3_stmt *statement = nullptr;
    if (sqlite3_prepare_v2(db_, sql, -1, &statement, nullptr) != SQLITE_OK) {
      throw std::runtime_error(sqlite3_errmsg(db_));
    }
    const int result = sqlite3_step(statement);
    const int value = sqlite3_column_int(statement, 0);
    sqlite3_finalize(statement);
    if (result != SQLITE_ROW) {
      throw std::runtime_error("test query returned no row");
    }
    return value;
  }

private:
  sqlite3 *db_ = nullptr;
};

void test_migration_and_restart(const std::filesystem::path &path) {
  {
    RawDatabase database(path);
    database.execute("CREATE TABLE intake_events ("
                     "device_id TEXT NOT NULL, boot_id TEXT NOT NULL, "
                     "sequence_number INTEGER NOT NULL, mqtt_payload TEXT NOT NULL, "
                     "gateway_received_at TEXT NOT NULL, "
                     "PRIMARY KEY (device_id, boot_id, sequence_number)) WITHOUT ROWID");
    database.execute("INSERT INTO intake_events VALUES "
                     "('device-1', 'boot-1', 1, '{\"reading\":1}', "
                     "'2026-01-01T00:00:00.000Z')");
  }

  gateway::telemetry::Event original{"device-1", "boot-1", 1, "{\"reading\":1}",
                                     "2026-01-01T00:00:00.000Z"};
  gateway::telemetry::Event next{"device-1", "boot-1", 2, "{\"reading\":2}",
                                 "2026-01-01T00:00:01.000Z"};
  {
    gateway::sqlite::Store store(path);
    gateway::Forwarder forwarder(store);
    auto pending = forwarder.load_pending();
    expect(pending.size() == 1, "migration must expose the old persisted event");
    expect(pending[0].event.mqtt_payload == original.mqtt_payload &&
               pending[0].event.gateway_received_at == original.gateway_received_at,
           "migration changed original content or receipt time");
    expect(pending[0].state == gateway::sqlite::QueueState::pending &&
               pending[0].attempt_count == 0,
           "migration must initialize queue metadata");

    auto retry = original;
    retry.gateway_received_at = "2027-01-01T00:00:00.000Z";
    expect(store.insert(retry) == gateway::sqlite::Store::InsertResult::duplicate,
           "same identity and content must be a duplicate");
    retry.mqtt_payload = "{\"reading\":99}";
    expect(store.insert(retry) == gateway::sqlite::Store::InsertResult::identity_conflict,
           "conflicting content must not overwrite a row");
    expect(forwarder.load_pending().size() == 1, "forwarder must see only persisted rows");

    expect(store.insert(next) == gateway::sqlite::Store::InsertResult::inserted,
           "new event must insert");
    {
      RawDatabase independent_reader(path);
      expect(independent_reader.scalar("SELECT COUNT(*) FROM intake_events") == 2,
             "insert must commit before return");
      expect(independent_reader.scalar("PRAGMA user_version") == 1,
             "migration must set schema version");
    }

    auto claimed = forwarder.claim_pending(1);
    expect(claimed.size() == 1 && claimed[0].event.sequence_number == 1 &&
               claimed[0].state == gateway::sqlite::QueueState::in_flight &&
               claimed[0].attempt_count == 1,
           "claim must mark oldest committed event and increment attempts");
    expect(forwarder.load_pending().size() == 1 && store.pending_count() == 1,
           "in-flight event must not be pending");
    expect(store.insert(retry) == gateway::sqlite::Store::InsertResult::identity_conflict,
           "conflicting duplicate must not replace an in-flight event");
    {
      RawDatabase independent_reader(path);
      expect(independent_reader.scalar("SELECT attempt_count FROM intake_events WHERE "
                                       "sequence_number=1") == 1,
             "attempt count must be committed before forwarding");
      expect(independent_reader.scalar("SELECT COUNT(*) FROM intake_events WHERE "
                                       "sequence_number=1 AND queue_state='in_flight'") == 1,
             "duplicate must not reset claim state");
    }
    expect(forwarder.release_claim(claimed[0]), "claim must be releasable");
    auto reclaimed = forwarder.claim_pending(1);
    expect(reclaimed.size() == 1 && reclaimed[0].attempt_count == 2,
           "retry must retain and increase attempt count");
    expect(!forwarder.release_claim(claimed[0]), "stale claim must not release newer attempt");
    store.close(); // Simulate process exit with one abandoned in-flight row.
  }

  {
    gateway::sqlite::Store store(path);
    gateway::Forwarder forwarder(store);
    const auto recovered = forwarder.load_pending();
    expect(recovered.size() == 2 && store.pending_count() == 2,
           "restart must recover in-flight and pending rows");
    expect(recovered[0].event.mqtt_payload == original.mqtt_payload &&
               recovered[0].event.gateway_received_at == original.gateway_received_at &&
               recovered[0].attempt_count == 2,
           "recovery must preserve original content, receipt, and attempts");
    expect(recovered[1].event.mqtt_payload == next.mqtt_payload && recovered[1].attempt_count == 0,
           "restart must preserve the second queued event");
    store.close();
  }
}

} // namespace

int main() {
  TemporaryDirectory directory;
  test_migration_and_restart(directory.path / "queue.sqlite3");
}
