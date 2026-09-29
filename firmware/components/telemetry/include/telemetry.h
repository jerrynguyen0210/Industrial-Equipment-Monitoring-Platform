#pragma once

#include <stdint.h>

#include "app_config.h"
#include "esp_err.h"
#include "identity.h"

// MQTT and its bounded RAM queue own copies of each successfully sampled value.
// The identity is used only by the sampling task when creating a new event.
esp_err_t telemetry_start(const app_config_t *config, identity_t *identity);
void telemetry_submit_temperature(float celsius);
