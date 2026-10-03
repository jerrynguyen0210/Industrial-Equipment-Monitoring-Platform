#include "temperature_sensor.h"

#include <math.h>
#include <stdbool.h>
#include <stdlib.h>

#include "ds18b20.h"
#include "onewire_bus.h"

struct temperature_sensor {
  onewire_bus_handle_t bus;
  ds18b20_device_handle_t device;
};

esp_err_t temperature_sensor_create(int gpio, temperature_sensor_t **out) {
  if (out == NULL) {
    return ESP_ERR_INVALID_ARG;
  }
  *out = NULL;

  temperature_sensor_t *sensor = calloc(1, sizeof(*sensor));
  if (sensor == NULL) {
    return ESP_ERR_NO_MEM;
  }

  onewire_bus_config_t bus_config = {
      .bus_gpio_num = gpio,
      .flags = {.en_pull_up = true},
  };
  onewire_bus_rmt_config_t rmt_config = {.max_rx_bytes = 10};
  esp_err_t err = onewire_new_bus_rmt(&bus_config, &rmt_config, &sensor->bus);
  if (err == ESP_OK) {
    // This mode addresses a single probe. Presence is checked on every read,
    // so plugging in the not-yet-installed probe needs no firmware restart.
    ds18b20_config_t device_config = {};
    err = ds18b20_new_device_from_bus(sensor->bus, &device_config, &sensor->device);
  }
  if (err != ESP_OK) {
    temperature_sensor_destroy(sensor);
    return err;
  }

  *out = sensor;
  return ESP_OK;
}

void temperature_sensor_destroy(temperature_sensor_t *sensor) {
  if (sensor == NULL) {
    return;
  }
  if (sensor->device != NULL) {
    ds18b20_del_device(sensor->device);
  }
  if (sensor->bus != NULL) {
    onewire_bus_del(sensor->bus);
  }
  free(sensor);
}

static temperature_sample_t sample_error(esp_err_t err) {
  temperature_sample_t sample = {.status = TEMPERATURE_SAMPLE_IO_ERROR, .driver_error = err};
  switch (err) {
  case ESP_ERR_NOT_FOUND:
    sample.status = TEMPERATURE_SAMPLE_DISCONNECTED;
    break;
  case ESP_ERR_INVALID_CRC:
    sample.status = TEMPERATURE_SAMPLE_CRC_ERROR;
    break;
  case ESP_ERR_INVALID_STATE:
    sample.status = TEMPERATURE_SAMPLE_INVALID;
    break;
  default:
    break;
  }
  return sample;
}

temperature_sample_t temperature_sensor_read(temperature_sensor_t *sensor) {
  if (sensor == NULL) {
    return sample_error(ESP_ERR_INVALID_ARG);
  }

  esp_err_t err = ds18b20_trigger_temperature_conversion(sensor->device);
  if (err != ESP_OK) {
    return sample_error(err);
  }

  float celsius;
  err = ds18b20_get_temperature(sensor->device, &celsius);
  if (err != ESP_OK) {
    return sample_error(err);
  }
  if (!isfinite(celsius) || celsius < -55.0f || celsius > 125.0f) {
    return (temperature_sample_t){.status = TEMPERATURE_SAMPLE_INVALID,
                                  .driver_error = ESP_ERR_INVALID_RESPONSE};
  }
  return (temperature_sample_t){
      .status = TEMPERATURE_SAMPLE_VALID, .celsius = celsius, .driver_error = ESP_OK};
}
