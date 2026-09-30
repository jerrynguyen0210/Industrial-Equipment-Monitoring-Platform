#include "boot_id.h"

#include <inttypes.h>
#include <stdio.h>

#include "esp_mac.h"
#include "nvs.h"

esp_err_t boot_id_create(char out[IEMP_BOOT_ID_SIZE]) {
  if (out == NULL) {
    return ESP_ERR_INVALID_ARG;
  }

  uint8_t mac[6];
  esp_err_t err = esp_efuse_mac_get_default(mac);
  if (err != ESP_OK) {
    return err;
  }

  nvs_handle_t handle;
  err = nvs_open("iemp_boot", NVS_READWRITE, &handle);
  if (err != ESP_OK) {
    return err;
  }

  uint64_t counter = 0;
  err = nvs_get_u64(handle, "counter", &counter);
  if (err == ESP_ERR_NVS_NOT_FOUND) {
    err = ESP_OK;
  }
  if (err == ESP_OK && counter == UINT64_MAX) {
    err = ESP_ERR_INVALID_STATE;
  }
  if (err == ESP_OK) {
    ++counter;
    err = nvs_set_u64(handle, "counter", counter);
  }
  if (err == ESP_OK) {
    err = nvs_commit(handle);
  }
  nvs_close(handle);
  if (err != ESP_OK) {
    return err;
  }

  const int written = snprintf(out, IEMP_BOOT_ID_SIZE, "%02x%02x%02x%02x%02x%02x-%016" PRIx64,
                               mac[0], mac[1], mac[2], mac[3], mac[4], mac[5], counter);
  return written == IEMP_BOOT_ID_SIZE - 1 ? ESP_OK : ESP_FAIL;
}
