#include <assert.h>
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
  puts("telemetry encoding checks passed");
  return 0;
}
