#pragma once

#include "esp_err.h"

typedef struct temperature_sensor temperature_sensor_t;

typedef enum {
  TEMPERATURE_SAMPLE_VALID,
  TEMPERATURE_SAMPLE_DISCONNECTED,
  TEMPERATURE_SAMPLE_CRC_ERROR,
  TEMPERATURE_SAMPLE_INVALID,
  TEMPERATURE_SAMPLE_IO_ERROR,
} temperature_sample_status_t;

typedef struct {
  temperature_sample_status_t status;
  // Set only for TEMPERATURE_SAMPLE_VALID. Never publish or log on another status.
  float celsius;
  esp_err_t driver_error;
} temperature_sample_t;

// One externally powered DS18B20 on a dedicated 1-Wire bus. The caller owns the
// returned context and must access it from one task at a time.
esp_err_t temperature_sensor_create(int gpio, temperature_sensor_t **out);
void temperature_sensor_destroy(temperature_sensor_t *sensor);
temperature_sample_t temperature_sensor_read(temperature_sensor_t *sensor);
