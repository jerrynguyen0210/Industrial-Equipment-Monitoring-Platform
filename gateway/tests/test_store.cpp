#include "gateway/forwarder.hpp"
#include "gateway/http/client.hpp"
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

class FakeHttpClient : public gateway::http::Client {
public:
  gateway::http::Response response{200, ""};
  bool fail = false;
  std::string posted;

  gateway::http::Response post_batch(std::string_view body) override {
    posted = std::string(body);
    if (fail) {
      throw std::runtime_error("simulated connection failure");
    }
    return response;
  }
  void stop() override {}
};

gateway::telemetry::Event delivery_event(int sequence) {
  const auto number = std::to_string(sequence);
  return {"device-1", "boot-1", sequence,
          "{\"schema_version\":1,\"device_id\":\"device-1\",\"boot_id\":\"boot-1\","
          "\"sequence_number\":" +
              number +
              ",\"measured_at\":null,\"device_uptime_ms\":1,\"metric\":\"temperature\","
              "\"value\":31.4000000000000000000000001,\"unit\":\"celsius\","
              "\"quality\":{\"reading\":\"valid\",\"clock\":\"unsynchronised\"}}",
          "2026-01-01T00:00:00.000Z"};
}

void test_delivery_outcomes(const std::filesystem::path &path) {
  gateway::sqlite::Store store(path);
  gateway::Forwarder forwarder(store);
  FakeHttpClient client;
  for (int sequence = 1; sequence <= 3; ++sequence) {
    expect(store.insert(delivery_event(sequence)) == gateway::sqlite::Store::InsertResult::inserted,
           "delivery test event must insert");
  }
  client.response.body = "{\"batch_id\":\"batch-1\",\"results\":["
                         "{\"device_id\":\"device-1\",\"boot_id\":\"boot-1\",\"sequence_number\":1,"
                         "\"outcome\":\"accepted\"},"
                         "{\"device_id\":\"device-1\",\"boot_id\":\"boot-1\",\"sequence_number\":2,"
                         "\"outcome\":\"duplicate\"},"
                         "{\"device_id\":\"device-1\",\"boot_id\":\"boot-1\",\"sequence_number\":3,"
                         "\"outcome\":\"rejected\",\"reason\":\"unknown_device\"}]}";
  expect(forwarder.drain_once(client) == gateway::Forwarder::RunResult::delivered,
         "mixed response must apply");
  expect(client.posted.find("31.4000000000000000000000001") != std::string::npos,
         "forwarding must preserve precise JSON number text");
  expect(client.posted.find("\"gateway_received_at\":\"2026-01-01T00:00:00.000Z\"") !=
             std::string::npos,
         "forwarding must include original gateway receipt time");
  expect(client.posted.find("\"schema_version\":1,\"device_id\"") == std::string::npos,
         "event-level schema version must be removed");
  {
    RawDatabase database(path);
    expect(database.scalar("SELECT COUNT(*) FROM intake_events") == 0,
           "confirmed and rejected rows must leave the queue");
    expect(database.scalar("SELECT COUNT(*) FROM quarantined_events WHERE "
                           "sequence_number=3 AND reason='unknown_device'") == 1,
           "permanent rejection must enter quarantine");
  }
  expect(store.insert(delivery_event(3)) == gateway::sqlite::Store::InsertResult::duplicate,
         "quarantined retransmission must not re-enter queue");

  expect(store.insert(delivery_event(4)) == gateway::sqlite::Store::InsertResult::inserted,
         "retry test event must insert");
  client.fail = true;
  expect(forwarder.drain_once(client) == gateway::Forwarder::RunResult::retry,
         "connection failure must request retry");
  expect(store.pending_count() == 1 && forwarder.load_pending()[0].attempt_count == 1,
         "connection failure must retain the event and its attempt count");
  client.fail = false;
  client.response.body =
      "{\"batch_id\":\"batch-2\",\"results\":[{\"device_id\":\"device-1\","
      "\"boot_id\":\"boot-1\",\"sequence_number\":999,\"outcome\":\"accepted\"}]}";
  expect(forwarder.drain_once(client) == gateway::Forwarder::RunResult::retry,
         "mismatched response must not delete data");
  expect(store.pending_count() == 1 && forwarder.load_pending()[0].attempt_count == 2,
         "mismatched response must retain the event");
  store.close();
  gateway::sqlite::Store reopened(path);
  expect(reopened.pending_count() == 1 && reopened.load_pending(1)[0].attempt_count == 2,
         "failed delivery must survive restart");
  gateway::Forwarder recovered_forwarder(reopened);
  client.response.body = "{\"batch_id\":\"batch-3\",\"results\":[{\"device_id\":\"device-1\","
                         "\"boot_id\":\"boot-1\",\"sequence_number\":4,\"outcome\":\"accepted\","
                         "\"outcome\":\"rejected\",\"reason\":\"unknown_device\"}]}";
  expect(recovered_forwarder.drain_once(client) == gateway::Forwarder::RunResult::retry,
         "contradictory response keys must not delete data");
  expect(reopened.pending_count() == 1, "contradictory response must leave the event pending");
}

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
      expect(independent_reader.scalar("PRAGMA user_version") == 2,
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
  test_delivery_outcomes(directory.path / "delivery.sqlite3");
}
