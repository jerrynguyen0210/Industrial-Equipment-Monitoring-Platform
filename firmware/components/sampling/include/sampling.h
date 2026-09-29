#pragma once

#include "esp_err.h"

// Starts a dedicated periodic task; Wi-Fi state never controls sampling.
esp_err_t sampling_start(void);
