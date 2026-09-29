#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef struct {
  const char *device_id;
  const char *boot_id;
  int64_t sequence_number;
  int64_t device_uptime_ms;
  float celsius;
  // Empty when no trustworthy UTC time existed at measurement.
  const char *measured_at;
} telemetry_event_t;

// Encodes exactly one MQTT schema v1 event. Returns false on invalid input or
// insufficient output space. A caller must retain the result for QoS 1 retries.
bool telemetry_encode(const telemetry_event_t *event, char *out, size_t capacity);
