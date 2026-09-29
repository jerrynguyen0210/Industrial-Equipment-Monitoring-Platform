#include "gateway/config.hpp"

#include <array>
#include <cctype>
#include <charconv>
#include <cstdlib>
#include <fstream>
#include <map>
#include <stdexcept>
#include <string_view>
#include <system_error>

namespace gateway {
namespace {

constexpr std::array<std::string_view, 7> keys = {
    "MQTT_HOST",    "MQTT_PORT",       "MQTT_USERNAME", "MQTT_PASSWORD_FILE",
    "API_BASE_URL", "GATEWAY_API_KEY", "QUEUE_DB_PATH"};

std::string trim(std::string_view input) {
  while (!input.empty() && std::isspace(static_cast<unsigned char>(input.front()))) {
    input.remove_prefix(1);
  }
  while (!input.empty() && std::isspace(static_cast<unsigned char>(input.back()))) {
    input.remove_suffix(1);
  }
  return std::string(input);
}

bool known_key(std::string_view key) {
  for (const auto candidate : keys) {
    if (candidate == key) {
      return true;
    }
  }
  return false;
}

std::map<std::string, std::string> read_file(const std::filesystem::path &file) {
  std::ifstream input(file);
  if (!input) {
    throw std::runtime_error("cannot open config file '" + file.string() + "'");
  }

  std::map<std::string, std::string> values;
  std::string line;
  std::size_t line_number = 0;
  while (std::getline(input, line)) {
    ++line_number;
    const std::string stripped = trim(line);
    if (stripped.empty() || stripped.front() == '#') {
      continue;
    }
    const auto equals = stripped.find('=');
    if (equals == std::string::npos) {
      throw std::runtime_error("config line " + std::to_string(line_number) +
                               ": expected KEY=VALUE");
    }
    const std::string key = trim(std::string_view(stripped).substr(0, equals));
    if (!known_key(key)) {
      throw std::runtime_error("config line " + std::to_string(line_number) + ": unknown key '" +
                               key + "'");
    }
    std::string value = trim(std::string_view(stripped).substr(equals + 1));
    if (!value.empty() && (value.front() == '\'' || value.front() == '"')) {
      if (value.size() < 2 || value.back() != value.front()) {
        throw std::runtime_error("config line " + std::to_string(line_number) +
                                 ": unterminated quoted value for " + key);
      }
      value = value.substr(1, value.size() - 2);
    }
    if (value.find('\0') != std::string::npos || value.find('\n') != std::string::npos ||
        value.find('\r') != std::string::npos) {
      throw std::runtime_error("config line " + std::to_string(line_number) +
                               ": invalid control character for " + key);
    }
    if (!values.emplace(key, value).second) {
      throw std::runtime_error("config line " + std::to_string(line_number) + ": duplicate key '" +
                               key + "'");
    }
  }
  if (input.bad()) {
    throw std::runtime_error("error reading config file '" + file.string() + "'");
  }
  return values;
}

std::string required(const std::map<std::string, std::string> &values, std::string_view key) {
  const auto found = values.find(std::string(key));
  if (found == values.end() || found->second.empty()) {
    throw std::runtime_error("missing or empty setting " + std::string(key));
  }
  const auto &value = found->second;
  if (value.find('\n') != std::string::npos || value.find('\r') != std::string::npos) {
    throw std::runtime_error("invalid control character for " + std::string(key));
  }
  return value;
}

std::filesystem::path resolve(const std::filesystem::path &base, const std::string &value) {
  const std::filesystem::path path(value);
  return (path.is_absolute() ? path : base / path).lexically_normal();
}

void validate_api_url(const std::string &url) {
  const auto scheme_end = url.find("://");
  if (scheme_end == std::string::npos ||
      (url.substr(0, scheme_end) != "http" && url.substr(0, scheme_end) != "https")) {
    throw std::runtime_error("API_BASE_URL must use http:// or https://");
  }
  const auto authority_start = scheme_end + 3;
  const auto path_start = url.find('/', authority_start);
  if (path_start == std::string::npos || path_start == authority_start ||
      url.substr(path_start) != "/api" ||
      url.substr(authority_start, path_start - authority_start).find('@') != std::string::npos ||
      url.find_first_of(" \t\r\n?#") != std::string::npos) {
    throw std::runtime_error("API_BASE_URL must be a host URL ending in /api");
  }
}

} // namespace

Config load_config(const std::filesystem::path &file) {
  const auto absolute_file = std::filesystem::absolute(file);
  auto values = read_file(absolute_file);
  for (const auto key : keys) {
    if (const char *environment = std::getenv(std::string(key).c_str())) {
      values[std::string(key)] = environment;
    }
  }

  Config config;
  config.mqtt_host = required(values, "MQTT_HOST");
  if (config.mqtt_host.find_first_of("/ \t\r\n") != std::string::npos) {
    throw std::runtime_error("MQTT_HOST must be a hostname or IP address");
  }
  const std::string port = required(values, "MQTT_PORT");
  const auto parsed = std::from_chars(port.data(), port.data() + port.size(), config.mqtt_port);
  if (parsed.ec != std::errc{} || parsed.ptr != port.data() + port.size() || config.mqtt_port < 1 ||
      config.mqtt_port > 65535) {
    throw std::runtime_error("MQTT_PORT must be an integer from 1 to 65535");
  }
  config.mqtt_username = required(values, "MQTT_USERNAME");
  if (config.mqtt_username.find_first_of(" \t\r\n") != std::string::npos) {
    throw std::runtime_error("MQTT_USERNAME must not contain whitespace");
  }
  config.mqtt_password_file =
      resolve(absolute_file.parent_path(), required(values, "MQTT_PASSWORD_FILE"));
  std::ifstream password(config.mqtt_password_file);
  if (!password || password.peek() == std::char_traits<char>::eof()) {
    throw std::runtime_error("MQTT_PASSWORD_FILE must name a readable, nonempty file");
  }
  config.api_base_url = required(values, "API_BASE_URL");
  validate_api_url(config.api_base_url);
  config.gateway_api_key = required(values, "GATEWAY_API_KEY");
  if (config.gateway_api_key.rfind("replace-with-", 0) == 0) {
    throw std::runtime_error("GATEWAY_API_KEY still contains the example placeholder");
  }
  config.queue_db_path = resolve(absolute_file.parent_path(), required(values, "QUEUE_DB_PATH"));
  if (std::filesystem::is_directory(config.queue_db_path)) {
    throw std::runtime_error("QUEUE_DB_PATH must name a file, not a directory");
  }
  return config;
}

} // namespace gateway
