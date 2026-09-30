#pragma once

#include "esp_err.h"
#include "onewire_bus.h"

typedef void *ds18b20_device_handle_t;
typedef struct {
} ds18b20_config_t;

esp_err_t ds18b20_new_device_from_bus(onewire_bus_handle_t bus, const ds18b20_config_t *config,
                                      ds18b20_device_handle_t *device);
esp_err_t ds18b20_del_device(ds18b20_device_handle_t device);
esp_err_t ds18b20_trigger_temperature_conversion(ds18b20_device_handle_t device);
esp_err_t ds18b20_get_temperature(ds18b20_device_handle_t device, float *temperature);
