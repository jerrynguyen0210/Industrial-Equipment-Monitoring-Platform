#pragma once

#include "app_config.h"
#include "esp_err.h"

// Starts the local form after Wi-Fi and the telemetry queue have been started.
esp_err_t web_input_start(const app_config_t *config);
