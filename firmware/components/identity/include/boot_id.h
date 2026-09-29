#pragma once

#include "esp_err.h"
#include "identity.h"

// Requires nvs_flash_init(). Commits a new counter before returning the ID.
esp_err_t boot_id_create(char out[IEMP_BOOT_ID_SIZE]);
