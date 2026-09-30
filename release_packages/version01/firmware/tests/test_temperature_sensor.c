#include <assert.h>
#include <math.h>
#include <stddef.h>

#include "ds18b20.h"
#include "onewire_bus.h"
#include "temperature_sensor.h"

static esp_err_t bus_init_error;
static esp_err_t device_init_error;
static esp_err_t trigger_error;
static esp_err_t read_error;
static float next_temperature;
static int bus_deletes;
static int device_deletes;

esp_err_t onewire_new_bus_rmt(const onewire_bus_config_t *config,
                              const onewire_bus_rmt_config_t *rmt_config,
                              onewire_bus_handle_t *bus) {
  assert(config->bus_gpio_num == 4);
  assert(config->flags.en_pull_up);
  assert(rmt_config->max_rx_bytes == 10);
  if (bus_init_error != ESP_OK) {
    return bus_init_error;
  }
  *bus = (void *)1;
  return ESP_OK;
}

esp_err_t onewire_bus_del(onewire_bus_handle_t bus) {
  assert(bus == (void *)1);
  ++bus_deletes;
  return ESP_OK;
}

esp_err_t ds18b20_new_device_from_bus(onewire_bus_handle_t bus, const ds18b20_config_t *config,
                                      ds18b20_device_handle_t *device) {
  assert(bus == (void *)1 && config != NULL);
  if (device_init_error != ESP_OK) {
    return device_init_error;
  }
  *device = (void *)2;
  return ESP_OK;
}

esp_err_t ds18b20_del_device(ds18b20_device_handle_t device) {
  assert(device == (void *)2);
  ++device_deletes;
  return ESP_OK;
}

esp_err_t ds18b20_trigger_temperature_conversion(ds18b20_device_handle_t device) {
  assert(device == (void *)2);
  return trigger_error;
}

esp_err_t ds18b20_get_temperature(ds18b20_device_handle_t device, float *temperature) {
  assert(device == (void *)2 && temperature != NULL);
  if (read_error != ESP_OK) {
    return read_error;
  }
  *temperature = next_temperature;
  return ESP_OK;
}

int main(void) {
  temperature_sensor_destroy(NULL);
  temperature_sample_t invalid_context = temperature_sensor_read(NULL);
  assert(invalid_context.status == TEMPERATURE_SAMPLE_IO_ERROR);
  assert(invalid_context.driver_error == ESP_ERR_INVALID_ARG);

  temperature_sensor_t *sensor = (void *)1;
  assert(temperature_sensor_create(4, NULL) == ESP_ERR_INVALID_ARG);

  bus_init_error = ESP_FAIL;
  assert(temperature_sensor_create(4, &sensor) == ESP_FAIL);
  assert(sensor == NULL && bus_deletes == 0);
  bus_init_error = ESP_OK;

  device_init_error = ESP_ERR_NO_MEM;
  assert(temperature_sensor_create(4, &sensor) == ESP_ERR_NO_MEM);
  assert(sensor == NULL && bus_deletes == 1);
  device_init_error = ESP_OK;

  assert(temperature_sensor_create(4, &sensor) == ESP_OK);
  assert(sensor != NULL);

  trigger_error = ESP_ERR_NOT_FOUND;
  temperature_sample_t sample = temperature_sensor_read(sensor);
  assert(sample.status == TEMPERATURE_SAMPLE_DISCONNECTED);
  assert(sample.driver_error == ESP_ERR_NOT_FOUND);

  trigger_error = ESP_OK;
  next_temperature = 23.5f;
  sample = temperature_sensor_read(sensor);
  assert(sample.status == TEMPERATURE_SAMPLE_VALID && sample.celsius == 23.5f);

  next_temperature = 0.0f;
  sample = temperature_sensor_read(sensor);
  assert(sample.status == TEMPERATURE_SAMPLE_VALID && sample.celsius == 0.0f);

  read_error = ESP_ERR_INVALID_CRC;
  sample = temperature_sensor_read(sensor);
  assert(sample.status == TEMPERATURE_SAMPLE_CRC_ERROR);

  read_error = ESP_ERR_INVALID_STATE;
  sample = temperature_sensor_read(sensor);
  assert(sample.status == TEMPERATURE_SAMPLE_INVALID);

  read_error = ESP_OK;
  next_temperature = NAN;
  sample = temperature_sensor_read(sensor);
  assert(sample.status == TEMPERATURE_SAMPLE_INVALID);
  next_temperature = 126.0f;
  sample = temperature_sensor_read(sensor);
  assert(sample.status == TEMPERATURE_SAMPLE_INVALID);

  temperature_sensor_destroy(sensor);
  assert(device_deletes == 1 && bus_deletes == 2);
  return 0;
}
