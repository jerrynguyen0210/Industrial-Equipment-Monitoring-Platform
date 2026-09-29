#include <inttypes.h>

#include "app_config.h"
#include "boot_id.h"
#include "esp_app_desc.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_system.h"
#include "identity.h"
#include "nvs_flash.h"
#include "wifi_station.h"

static const char *TAG = "firmware";
static identity_t s_identity;

void app_main(void) {
  // Never erase NVS on an initialization error: that could reuse a boot ID.
  esp_err_t err = nvs_flash_init();
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "startup_failed stage=nvs error=%s", esp_err_to_name(err));
    return;
  }

  char boot_id[IEMP_BOOT_ID_SIZE];
  err = boot_id_create(boot_id);
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "startup_failed stage=boot_id error=%s", esp_err_to_name(err));
    return;
  }

  if (!identity_init(&s_identity, boot_id)) {
    ESP_LOGE(TAG, "startup_failed stage=identity");
    return;
  }

  ESP_LOGI(TAG,
           "identity_ready boot_id=%s sequence_next=%" PRIu64
           " reset_reason=%d firmware_version=%s",
           s_identity.boot_id, s_identity.next_sequence, (int)esp_reset_reason(),
           esp_app_get_description()->version);

  app_config_t config;
  err = app_config_load(&config);
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "startup_failed stage=config error=%s", esp_err_to_name(err));
    return;
  }
  ESP_LOGI(TAG, "config_ready device_id=%s", config.device_id);

  err = wifi_station_start(&config);
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "startup_failed stage=wifi error=%s", esp_err_to_name(err));
    return;
  }

  // The identity remains available for the telemetry component added later.
  // A sequence is allocated only when an event is created, never on reconnect.
}
