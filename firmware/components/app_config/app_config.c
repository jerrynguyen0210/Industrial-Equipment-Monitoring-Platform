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
  if (device_id_length == 0 || device_id_length > 128 ||
      strpbrk(CONFIG_IEMP_DEVICE_ID, "/+#") != NULL) {
    ESP_LOGE(TAG, "invalid_config field=device_id");
    return ESP_ERR_INVALID_ARG;
  }
  for (size_t index = 0; index < device_id_length; ++index) {
    const unsigned char character = (unsigned char)CONFIG_IEMP_DEVICE_ID[index];
    if (character < 0x20 || character == 0x7f) {
      ESP_LOGE(TAG, "invalid_config field=device_id");
      return ESP_ERR_INVALID_ARG;
    }
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

  if (CONFIG_IEMP_MQTT_HOST[0] == '\0' || strlen(CONFIG_IEMP_MQTT_HOST) > 253) {
    ESP_LOGE(TAG, "invalid_config field=mqtt_host");
    return ESP_ERR_INVALID_ARG;
  }
  if (CONFIG_IEMP_MQTT_PASSWORD[0] == '\0') {
    ESP_LOGE(TAG, "invalid_config field=mqtt_password");
    return ESP_ERR_INVALID_ARG;
  }
  if (strlen(CONFIG_IEMP_BACKEND_HOST) > 253) {
    ESP_LOGE(TAG, "invalid_config field=backend_host");
    return ESP_ERR_INVALID_ARG;
  }

#if CONFIG_IEMP_WEB_SENSOR_INPUT
  const size_t web_key_length = strlen(CONFIG_IEMP_WEB_INPUT_KEY);
  if (web_key_length < 8 || web_key_length > 63) {
    ESP_LOGE(TAG, "invalid_config field=web_input_key");
    return ESP_ERR_INVALID_ARG;
  }
  for (size_t index = 0; index < web_key_length; ++index) {
    const unsigned char character = (unsigned char)CONFIG_IEMP_WEB_INPUT_KEY[index];
    if (character < 0x21 || character > 0x7e) {
      ESP_LOGE(TAG, "invalid_config field=web_input_key");
      return ESP_ERR_INVALID_ARG;
    }
  }
#endif

  *out = (app_config_t){
      .device_id = CONFIG_IEMP_DEVICE_ID,
      .wifi_ssid = CONFIG_IEMP_WIFI_SSID,
      .wifi_password = CONFIG_IEMP_WIFI_PASSWORD,
      .mqtt_host = CONFIG_IEMP_MQTT_HOST,
      .mqtt_port = CONFIG_IEMP_MQTT_PORT,
      .mqtt_password = CONFIG_IEMP_MQTT_PASSWORD,
      .backend_host = CONFIG_IEMP_BACKEND_HOST,
      .backend_port = CONFIG_IEMP_BACKEND_PORT,
#if CONFIG_IEMP_WEB_SENSOR_INPUT
      .web_input_key = CONFIG_IEMP_WEB_INPUT_KEY,
#else
      .web_input_key = NULL,
#endif
  };
  return ESP_OK;
}
