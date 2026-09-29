#include "telemetry_encoding.h"

#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static bool append(char **cursor, size_t *remaining, const char *value) {
  size_t length = strlen(value);
  if (length >= *remaining) {
    return false;
  }
  memcpy(*cursor, value, length + 1);
  *cursor += length;
  *remaining -= length;
  return true;
}

static bool append_json_string(char **cursor, size_t *remaining, const char *value) {
  if (!append(cursor, remaining, "\"")) {
    return false;
  }
  for (const unsigned char *p = (const unsigned char *)value; *p != '\0'; ++p) {
    char escaped[7];
    if (*p == '"' || *p == '\\') {
      escaped[0] = '\\';
      escaped[1] = (char)*p;
      escaped[2] = '\0';
    } else if (*p < 0x20) {
      (void)snprintf(escaped, sizeof(escaped), "\\u%04x", *p);
    } else {
      escaped[0] = (char)*p;
      escaped[1] = '\0';
    }
    if (!append(cursor, remaining, escaped)) {
      return false;
    }
  }
  return append(cursor, remaining, "\"");
}

bool telemetry_encode(const telemetry_event_t *event, char *out, size_t capacity) {
  if (event == NULL || out == NULL || capacity == 0 || event->device_id == NULL ||
      event->boot_id == NULL || event->measured_at == NULL || event->device_id[0] == '\0' ||
      event->boot_id[0] == '\0' || strlen(event->device_id) > 128 || strlen(event->boot_id) > 128 ||
      event->sequence_number < 0 || event->device_uptime_ms < 0 || !isfinite(event->celsius) ||
      event->celsius < -55.0f || event->celsius > 125.0f) {
    return false;
  }

  char *cursor = out;
  size_t remaining = capacity;
  if (!append(&cursor, &remaining, "{\"schema_version\":1,\"device_id\":") ||
      !append_json_string(&cursor, &remaining, event->device_id) ||
      !append(&cursor, &remaining, ",\"boot_id\":") ||
      !append_json_string(&cursor, &remaining, event->boot_id)) {
    return false;
  }
  int written =
      snprintf(cursor, remaining,
               ",\"sequence_number\":%" PRId64 ",\"measured_at\":", event->sequence_number);
  if (written < 0 || (size_t)written >= remaining) {
    return false;
  }
  cursor += written;
  remaining -= (size_t)written;
  if (event->measured_at[0] == '\0') {
    if (!append(&cursor, &remaining, "null")) {
      return false;
    }
  } else if (!append_json_string(&cursor, &remaining, event->measured_at)) {
    return false;
  }
  written = snprintf(cursor, remaining,
                     ",\"device_uptime_ms\":%" PRId64
                     ",\"metric\":\"temperature\",\"value\":%.4f,\"unit\":\"celsius\","
                     "\"quality\":{\"reading\":\"valid\",\"clock\":\"%s\"}}",
                     event->device_uptime_ms, (double)event->celsius,
                     event->measured_at[0] == '\0' ? "unsynchronised" : "synchronised");
  return written >= 0 && (size_t)written < remaining;
}
