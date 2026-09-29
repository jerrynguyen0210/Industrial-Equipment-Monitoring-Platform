#pragma once

#include "esp_err.h"

typedef struct {
  const char *device_id;
  const char *wifi_ssid;
  const char *wifi_password;
  const char *mqtt_host;
  int mqtt_port;
  const char *mqtt_password;
} app_config_t;

// Pointers refer to compile-time sdkconfig strings and remain valid for the boot.
// Invalid fields are logged by name only; secrets are never logged.
esp_err_t app_config_load(app_config_t *out);
