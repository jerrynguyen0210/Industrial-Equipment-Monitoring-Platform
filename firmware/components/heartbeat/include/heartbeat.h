#pragma once

#include "app_config.h"
#include "esp_err.h"

// Reports this ESP32's presence even when it has no temperature reading.
esp_err_t heartbeat_start(const app_config_t *config);
