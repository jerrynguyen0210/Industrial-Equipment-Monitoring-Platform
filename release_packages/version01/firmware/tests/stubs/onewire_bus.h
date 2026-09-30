#pragma once

#include <stdbool.h>
#include <stddef.h>

#include "esp_err.h"

typedef void *onewire_bus_handle_t;

typedef struct {
  int bus_gpio_num;
  struct {
    bool en_pull_up;
  } flags;
} onewire_bus_config_t;

typedef struct {
  size_t max_rx_bytes;
} onewire_bus_rmt_config_t;

esp_err_t onewire_new_bus_rmt(const onewire_bus_config_t *config,
                              const onewire_bus_rmt_config_t *rmt_config,
                              onewire_bus_handle_t *bus);
esp_err_t onewire_bus_del(onewire_bus_handle_t bus);
