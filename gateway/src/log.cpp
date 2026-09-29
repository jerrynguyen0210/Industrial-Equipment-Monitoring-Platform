#include "gateway/log.hpp"

#include <chrono>
#include <ctime>
#include <iomanip>
#include <iostream>
#include <string>

namespace gateway {
namespace {

std::string escape(std::string_view input) {
  constexpr char hex[] = "0123456789abcdef";
  std::string result;
  result.reserve(input.size());
  for (const unsigned char character : input) {
    switch (character) {
    case '"':
      result += "\\\"";
      break;
    case '\\':
      result += "\\\\";
      break;
    case '\n':
      result += "\\n";
      break;
    case '\r':
      result += "\\r";
      break;
    case '\t':
      result += "\\t";
      break;
    default:
      if (character < 0x20) {
        result += "\\u00";
        result += hex[character >> 4];
        result += hex[character & 0x0f];
      } else {
        result += static_cast<char>(character);
      }
    }
  }
  return result;
}

std::string_view level_name(Level level) {
  switch (level) {
  case Level::info:
    return "info";
  case Level::warning:
    return "warning";
  case Level::error:
    return "error";
  }
  return "error";
}

} // namespace

void log(Level level, std::string_view component, std::string_view event,
         std::string_view message) {
  const auto now = std::chrono::system_clock::now();
  const auto milliseconds =
      std::chrono::duration_cast<std::chrono::milliseconds>(now.time_since_epoch()) % 1000;
  const std::time_t seconds = std::chrono::system_clock::to_time_t(now);
  std::tm utc{};
  gmtime_r(&seconds, &utc);
  std::ostream &output = level == Level::error ? std::cerr : std::cout;
  output << "{\"timestamp\":\"" << std::put_time(&utc, "%Y-%m-%dT%H:%M:%S") << '.' << std::setw(3)
         << std::setfill('0') << milliseconds.count() << "Z\",\"level\":\"" << level_name(level)
         << "\",\"component\":\"" << escape(component) << "\",\"event\":\"" << escape(event)
         << "\",\"message\":\"" << escape(message) << "\"}" << std::endl;
}

} // namespace gateway
