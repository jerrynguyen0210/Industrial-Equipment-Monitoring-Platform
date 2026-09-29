#include "app_config.h"

#include <stdbool.h>
#include <string.h>

#include "esp_log.h"
#include "sdkconfig.h"

static const char *TAG = "app_config";

esp_err_t app_config_load(app_config_t *out) {
  if (out == NULL) {
    return ESP_ERR_INVALID_ARG;
  }

  const size_t device_id_length = strlen(CONFIG_IEMP_DEVICE_ID);
  bool invalid_device_id = device_id_length == 0 || device_id_length > 128 ||
                           strpbrk(CONFIG_IEMP_DEVICE_ID, "/+#") != NULL;
  for (size_t index = 0; index < device_id_length; ++index) {
    const unsigned char character = (unsigned char)CONFIG_IEMP_DEVICE_ID[index];
    if (character < 0x20 || character == 0x7f) {
      invalid_device_id = true;
    }
  }
  if (invalid_device_id) {
    ESP_LOGE(TAG, "invalid_config field=device_id");
    return ESP_ERR_INVALID_ARG;
  }

  const size_t ssid_length = strlen(CONFIG_IEMP_WIFI_SSID);
  if (ssid_length == 0 || ssid_length > 32) {
    ESP_LOGE(TAG, "invalid_config field=wifi_ssid");
    return ESP_ERR_INVALID_ARG;
  }

  const size_t password_length = strlen(CONFIG_IEMP_WIFI_PASSWORD);
  if (password_length < 8 || password_length > 63) {
    ESP_LOGE(TAG, "invalid_config field=wifi_password");
    return ESP_ERR_INVALID_ARG;
  }

  *out = (app_config_t){
      .device_id = CONFIG_IEMP_DEVICE_ID,
      .wifi_ssid = CONFIG_IEMP_WIFI_SSID,
      .wifi_password = CONFIG_IEMP_WIFI_PASSWORD,
  };
  return ESP_OK;
}
