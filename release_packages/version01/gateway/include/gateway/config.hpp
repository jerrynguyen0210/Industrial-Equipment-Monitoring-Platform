#pragma once

#include <filesystem>
#include <string>

namespace gateway {

struct Config {
  std::string mqtt_host;
  int mqtt_port = 0;
  std::string mqtt_username;
  std::filesystem::path mqtt_password_file;
  std::string api_base_url;
  std::string gateway_api_key;
  std::filesystem::path queue_db_path;
};

// Values in the process environment override those in the file.
Config load_config(const std::filesystem::path &file);

} // namespace gateway
