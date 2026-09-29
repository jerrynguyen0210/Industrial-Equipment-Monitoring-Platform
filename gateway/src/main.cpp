#include "gateway/config.hpp"
#include "gateway/log.hpp"
#include "gateway/sqlite/store.hpp"

#include <pthread.h>
#include <signal.h>
#include <sys/stat.h>

#include <cstdlib>
#include <cstring>
#include <exception>
#include <iostream>
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
  try {
    gateway::sqlite::Store store(config.queue_db_path);
    gateway::log(gateway::Level::info, "lifecycle", "ready",
                 "gateway started; MQTT intake and HTTP forwarding are not enabled");

    int received_signal = 0;
    const int wait_result = sigwait(&shutdown_signals, &received_signal);
    if (wait_result != 0) {
      gateway::log(gateway::Level::error, "lifecycle", "signal_wait_failed",
                   std::strerror(wait_result));
      return 4;
    }
    gateway::log(gateway::Level::info, "lifecycle", "shutdown_requested",
                 received_signal == SIGTERM ? "SIGTERM received" : "SIGINT received");
    store.close();
    gateway::log(gateway::Level::info, "lifecycle", "stopped", "SQLite closed; gateway stopped");
    return 0;
  } catch (const std::exception &error) {
    gateway::log(gateway::Level::error, "sqlite", "storage_error", error.what());
    return 3;
  }
}
