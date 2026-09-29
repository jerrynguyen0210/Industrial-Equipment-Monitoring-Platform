#pragma once

#include "app_config.h"
#include "esp_err.h"

// Starts STA mode and registers asynchronous connection/IP logging handlers.
esp_err_t wifi_station_start(const app_config_t *config);
