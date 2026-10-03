#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "identity.h"
#include "telemetry_encoding.h"

int main(void) {
  identity_t identity;
  assert(identity_init(&identity, "abcdef123456-0000000000000001"));
  telemetry_event_t event = {
      .device_id = "device-demo-001",
      .boot_id = identity.boot_id,
      .device_uptime_ms = 5000,
      .celsius = -12.0625f,
      .measured_at = "",
  };
  assert(identity_next_sequence(&identity, &event.sequence_number));
  char first[768];
  assert(telemetry_encode(&event, first, sizeof(first)));
  assert(strcmp(first, "{\"schema_version\":1,\"device_id\":\"device-demo-001\","
                       "\"boot_id\":\"abcdef123456-0000000000000001\",\"sequence_number\":0,"
                       "\"measured_at\":null,\"device_uptime_ms\":5000,\"metric\":\"temperature\","
                       "\"value\":-12.0625,\"unit\":\"celsius\","
                       "\"quality\":{\"reading\":\"valid\",\"clock\":\"unsynchronised\"}}") == 0);
  char replay[768];
  assert(telemetry_encode(&event, replay, sizeof(replay)));
  assert(strcmp(first, replay) == 0);
  assert(identity_next_sequence(&identity, &event.sequence_number));
  event.measured_at = "2026-09-29T00:00:00.123Z";
  assert(telemetry_encode(&event, replay, sizeof(replay)));
  assert(strstr(replay, "\"sequence_number\":1") != NULL);
  assert(strstr(replay, "\"measured_at\":\"2026-09-29T00:00:00.123Z\"") != NULL);
  assert(strstr(replay, "\"clock\":\"synchronised\"") != NULL);

  event.device_id = "quoted\"device\\id";
  assert(telemetry_encode(&event, replay, sizeof(replay)));
  assert(strstr(replay, "quoted\\\"device\\\\id") != NULL);
  assert(!telemetry_encode(&event, replay, 20));

  // Every non-NUL JSON control byte must use the same six-byte escape.
  char control_id[32];
  char expected_escape[7];
  for (size_t index = 0; index < sizeof(control_id) - 1; ++index) {
    control_id[index] = (char)(index + 1);
  }
  control_id[sizeof(control_id) - 1] = '\0';
  event.device_id = control_id;
  assert(telemetry_encode(&event, replay, sizeof(replay)));
  for (unsigned int character = 1; character < 0x20; ++character) {
    assert(snprintf(expected_escape, sizeof(expected_escape), "\\u%04x", character) == 6);
    assert(strstr(replay, expected_escape) != NULL);
  }
  const size_t encoded_length = strlen(replay);
  assert(telemetry_encode(&event, first, encoded_length + 1));
  assert(strcmp(first, replay) == 0);
  for (size_t capacity = 0; capacity <= encoded_length; ++capacity) {
    memset(first, 0x5a, sizeof(first));
    assert(!telemetry_encode(&event, first, capacity));
    assert(first[capacity] == 0x5a);
  }

  char escaped_id[129];
  memset(escaped_id, '"', sizeof(escaped_id) - 1);
  escaped_id[sizeof(escaped_id) - 1] = '\0';
  event.device_id = escaped_id;
  assert(telemetry_encode(&event, replay, sizeof(replay)));
  char too_long_id[130];
  memset(too_long_id, 'x', sizeof(too_long_id) - 1);
  too_long_id[sizeof(too_long_id) - 1] = '\0';
  event.device_id = too_long_id;
  assert(!telemetry_encode(&event, replay, sizeof(replay)));
  event.device_id = escaped_id;
  event.celsius = 126.0f;
  assert(!telemetry_encode(&event, replay, sizeof(replay)));
  event.celsius = NAN;
  assert(!telemetry_encode(&event, replay, sizeof(replay)));
  event.celsius = INFINITY;
  assert(!telemetry_encode(&event, replay, sizeof(replay)));
  event.celsius = -55.0f;
  assert(telemetry_encode(&event, replay, sizeof(replay)));
  event.celsius = 125.0f;
  assert(telemetry_encode(&event, replay, sizeof(replay)));
  event.sequence_number = -1;
  assert(!telemetry_encode(&event, replay, sizeof(replay)));
  event.sequence_number = INT64_MAX;
  event.device_uptime_ms = -1;
  assert(!telemetry_encode(&event, replay, sizeof(replay)));
  event.device_uptime_ms = INT64_MAX;
  assert(telemetry_encode(&event, replay, sizeof(replay)));
  assert(!telemetry_encode(NULL, replay, sizeof(replay)));
  assert(!telemetry_encode(&event, NULL, sizeof(replay)));
  event.device_id = NULL;
  assert(!telemetry_encode(&event, replay, sizeof(replay)));
  event.device_id = "device-demo-001";
  event.boot_id = NULL;
  assert(!telemetry_encode(&event, replay, sizeof(replay)));
  event.boot_id = identity.boot_id;
  event.measured_at = NULL;
  assert(!telemetry_encode(&event, replay, sizeof(replay)));
  puts("telemetry encoding checks passed");
  return 0;
}
