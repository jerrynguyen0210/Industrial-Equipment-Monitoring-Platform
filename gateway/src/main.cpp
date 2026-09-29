#include "gateway/config.hpp"
#include "gateway/forwarder.hpp"
#include "gateway/intake.hpp"
#include "gateway/log.hpp"
#include "gateway/mqtt/client.hpp"
#include "gateway/sqlite/store.hpp"

#include <pthread.h>
#include <signal.h>
#include <sys/stat.h>

#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>

namespace {

struct Options {
  std::string config_file;
  bool check_config = false;
};

Options parse_options(int argc, char **argv) {
  Options options;
  for (int index = 1; index < argc; ++index) {
    const std::string argument = argv[index];
    if (argument == "--help") {
      std::cout << "Usage: gateway --config FILE [--check-config]\n";
      std::exit(0);
    }
    if (argument == "--config" && index + 1 < argc && options.config_file.empty()) {
      options.config_file = argv[++index];
    } else if (argument == "--check-config" && !options.check_config) {
      options.check_config = true;
    } else {
      throw std::runtime_error("invalid arguments; use --help for usage");
    }
  }
  if (options.config_file.empty()) {
    throw std::runtime_error("--config FILE is required; use --help for usage");
  }
  return options;
}

} // namespace

int main(int argc, char **argv) {
  sigset_t shutdown_signals;
  sigemptyset(&shutdown_signals);
  sigaddset(&shutdown_signals, SIGINT);
  sigaddset(&shutdown_signals, SIGTERM);
  const int mask_result = pthread_sigmask(SIG_BLOCK, &shutdown_signals, nullptr);
  if (mask_result != 0) {
    gateway::log(gateway::Level::error, "lifecycle", "signal_setup_failed",
                 std::strerror(mask_result));
    return 4;
  }

  Options options;
  try {
    options = parse_options(argc, argv);
  } catch (const std::exception &error) {
    gateway::log(gateway::Level::error, "config", "invalid_arguments", error.what());
    return 2;
  }

  gateway::Config config;
  try {
    config = gateway::load_config(options.config_file);
  } catch (const std::exception &error) {
    gateway::log(gateway::Level::error, "config", "invalid_config", error.what());
    return 2;
  }
  if (options.check_config) {
    gateway::log(gateway::Level::info, "config", "config_valid", "configuration validated");
    return 0;
  }

  // SQLite creates the database and any WAL files with owner-only permissions.
  umask(0077);
  std::unique_ptr<gateway::sqlite::Store> store;
  try {
    store = std::make_unique<gateway::sqlite::Store>(config.queue_db_path);
  } catch (const std::exception &error) {
    gateway::log(gateway::Level::error, "sqlite", "storage_error", error.what());
    return 3;
  }
  try {
    gateway::Forwarder forwarder(*store);
    const auto loaded_count = forwarder.load_pending().size();
    const auto pending_total = store->pending_count();
    gateway::log(gateway::Level::info, "queue", "pending_loaded",
                 std::to_string(loaded_count) + " of " + std::to_string(pending_total) +
                     " pending rows loaded from SQLite");
    gateway::Intake intake(*store, gateway::utc_now);
    gateway::mqtt::Client client(config,
                                 [&](std::string_view topic, std::string_view payload,
                                     bool retained) { intake.receive(topic, payload, retained); });
    client.start();
    gateway::log(gateway::Level::info, "lifecycle", "ready",
                 "gateway started; MQTT connecting; HTTP forwarding is not enabled");

    int received_signal = 0;
    int exit_code = 0;
    while (received_signal == 0 && !client.failed()) {
      const timespec timeout{1, 0};
      const int result = sigtimedwait(&shutdown_signals, nullptr, &timeout);
      if (result == SIGTERM || result == SIGINT) {
        received_signal = result;
      } else if (result < 0 && errno != EAGAIN && errno != EINTR) {
        gateway::log(gateway::Level::error, "lifecycle", "signal_wait_failed",
                     std::strerror(errno));
        exit_code = 4;
        break;
      }
    }
    if (client.failed()) {
      gateway::log(gateway::Level::error, "lifecycle", "intake_failed",
                   "MQTT intake stopped after an internal error");
      exit_code = 5;
    } else if (received_signal != 0) {
      gateway::log(gateway::Level::info, "lifecycle", "shutdown_requested",
                   received_signal == SIGTERM ? "SIGTERM received" : "SIGINT received");
    }
    client.stop();
    store->close();
    gateway::log(gateway::Level::info, "lifecycle", "stopped", "SQLite closed; gateway stopped");
    return exit_code;
  } catch (const std::exception &error) {
    gateway::log(gateway::Level::error, "lifecycle", "runtime_error", error.what());
    return 3;
  }
}
