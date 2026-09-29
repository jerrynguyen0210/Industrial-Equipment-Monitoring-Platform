#include "wifi_station.h"

#include <inttypes.h>
#include <string.h>

#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_random.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"

static const char *TAG = "wifi_station";
static QueueHandle_t s_events;

typedef enum {
  WIFI_SIGNAL_STARTED,
  WIFI_SIGNAL_DISCONNECTED,
  WIFI_SIGNAL_GOT_IP,
} wifi_signal_t;

static void send_signal(wifi_signal_t signal) {
  if (xQueueSend(s_events, &signal, 0) != pdTRUE) {
    ESP_LOGE(TAG, "state_signal_dropped signal=%d", (int)signal);
  }
}

static void schedule_retry(uint32_t *cap_ms, uint32_t *delay_ms) {
  // Equal jitter: between half the cap and the cap, capped at 30 seconds.
  *delay_ms = *cap_ms / 2 + esp_random() % (*cap_ms / 2 + 1);
  ESP_LOGW(TAG, "state=retry_wait retry_in_ms=%" PRIu32, *delay_ms);
  *cap_ms = *cap_ms < 15000 ? *cap_ms * 2 : 30000;
}

static void attempt_connect(uint32_t *cap_ms, uint32_t *delay_ms) {
  ESP_LOGI(TAG, "state=connecting");
  esp_err_t err = esp_wifi_connect();
  if (err != ESP_OK) {
    ESP_LOGW(TAG, "connect_failed error=%s", esp_err_to_name(err));
    schedule_retry(cap_ms, delay_ms);
  }
}

static void connection_task(void *arg) {
  (void)arg;
  uint32_t cap_ms = 1000;
  uint32_t delay_ms = 0;
  wifi_signal_t signal;

  for (;;) {
    const TickType_t wait = delay_ms == 0 ? portMAX_DELAY : pdMS_TO_TICKS(delay_ms);
    if (xQueueReceive(s_events, &signal, wait) != pdTRUE) {
      delay_ms = 0;
      attempt_connect(&cap_ms, &delay_ms);
      continue;
    }

    switch (signal) {
    case WIFI_SIGNAL_STARTED:
      delay_ms = 0;
      attempt_connect(&cap_ms, &delay_ms);
      break;
    case WIFI_SIGNAL_DISCONNECTED:
      schedule_retry(&cap_ms, &delay_ms);
      break;
    case WIFI_SIGNAL_GOT_IP:
      cap_ms = 1000;
      delay_ms = 0;
      break;
    }
  }
}

static void on_wifi_event(void *arg, esp_event_base_t base, int32_t event_id, void *data) {
  (void)arg;
  (void)base;

  if (event_id == WIFI_EVENT_STA_START) {
    send_signal(WIFI_SIGNAL_STARTED);
  } else if (event_id == WIFI_EVENT_STA_DISCONNECTED) {
    const wifi_event_sta_disconnected_t *event = data;
    ESP_LOGW(TAG, "state=disconnected reason=%u", (unsigned)event->reason);
    send_signal(WIFI_SIGNAL_DISCONNECTED);
  }
}

static void on_ip_event(void *arg, esp_event_base_t base, int32_t event_id, void *data) {
  (void)arg;
  (void)base;
  (void)event_id;
  const ip_event_got_ip_t *event = data;
  ESP_LOGI(TAG, "state=connected ip=" IPSTR, IP2STR(&event->ip_info.ip));
  send_signal(WIFI_SIGNAL_GOT_IP);
}

esp_err_t wifi_station_start(const app_config_t *config) {
  if (config == NULL) {
    return ESP_ERR_INVALID_ARG;
  }

  esp_err_t err = esp_netif_init();
  if (err != ESP_OK) {
    return err;
  }
  err = esp_event_loop_create_default();
  if (err != ESP_OK) {
    return err;
  }
  if (esp_netif_create_default_wifi_sta() == NULL) {
    return ESP_ERR_NO_MEM;
  }

  wifi_init_config_t init_config = WIFI_INIT_CONFIG_DEFAULT();
  err = esp_wifi_init(&init_config);
  if (err != ESP_OK) {
    return err;
  }
  err = esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_wifi_event, NULL);
  if (err != ESP_OK) {
    return err;
  }
  err = esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_ip_event, NULL);
  if (err != ESP_OK) {
    return err;
  }

  wifi_config_t wifi_config = {0};
  memcpy(wifi_config.sta.ssid, config->wifi_ssid, strlen(config->wifi_ssid));
  memcpy(wifi_config.sta.password, config->wifi_password, strlen(config->wifi_password));
  wifi_config.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;
  wifi_config.sta.pmf_cfg.capable = true;
  wifi_config.sta.pmf_cfg.required = false;

  err = esp_wifi_set_storage(WIFI_STORAGE_RAM);
  if (err != ESP_OK) {
    return err;
  }
  err = esp_wifi_set_mode(WIFI_MODE_STA);
  if (err != ESP_OK) {
    return err;
  }
  err = esp_wifi_set_config(WIFI_IF_STA, &wifi_config);
  if (err != ESP_OK) {
    return err;
  }

  s_events = xQueueCreate(8, sizeof(wifi_signal_t));
  if (s_events == NULL) {
    return ESP_ERR_NO_MEM;
  }
  if (xTaskCreate(connection_task, "wifi_connection", 4096, NULL, 5, NULL) != pdPASS) {
    vQueueDelete(s_events);
    s_events = NULL;
    return ESP_ERR_NO_MEM;
  }

  ESP_LOGI(TAG, "state=starting");
  err = esp_wifi_start();
  return err;
}
