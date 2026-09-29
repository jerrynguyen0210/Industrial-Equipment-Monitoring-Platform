#pragma once

#include <stdint.h>

#include "app_config.h"
#include "esp_err.h"
#include "identity.h"

// MQTT and its bounded RAM queue own copies of each accepted temperature.
// The identity is used when a sensor or manual input creates a new event.
esp_err_t telemetry_start(const app_config_t *config, identity_t *identity);
// ESP_OK means queued in RAM, not delivered to the broker or backend.
esp_err_t telemetry_submit_temperature(float celsius);
