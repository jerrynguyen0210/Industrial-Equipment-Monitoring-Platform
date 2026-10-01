#include "heartbeat.h"

#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#include "cJSON.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define HEARTBEAT_INTERVAL_MS 30000

static const char *TAG = "heartbeat";
static app_config_t s_config;
static char s_url[768];

static bool encode_device_url(char *url, size_t capacity, const app_config_t *config) {
  int written = snprintf(url, capacity, "http://%s:%d/api/v1/devices/", config->backend_host,
                         config->backend_port);
  if (written < 0 || (size_t)written >= capacity) {
    return false;
  }
  size_t position = (size_t)written;
  const char *hex = "0123456789ABCDEF";
  for (const unsigned char *character = (const unsigned char *)config->device_id;
       *character != '\0'; ++character) {
    bool safe = (*character >= 'A' && *character <= 'Z') ||
                (*character >= 'a' && *character <= 'z') ||
                (*character >= '0' && *character <= '9') || *character == '-' ||
                *character == '_' || *character == '.' || *character == '~';
    size_t needed = safe ? 1 : 3;
    if (position + needed + sizeof("/heartbeat") > capacity) {
      return false;
    }
    if (safe) {
      url[position++] = (char)*character;
    } else {
      url[position++] = '%';
      url[position++] = hex[*character >> 4];
      url[position++] = hex[*character & 0x0f];
    }
  }
  memcpy(url + position, "/heartbeat", sizeof("/heartbeat"));
  return true;
}

static void send_heartbeat(void) {
  cJSON *body = cJSON_CreateObject();
  if (body == NULL || cJSON_AddStringToObject(body, "password", s_config.mqtt_password) == NULL) {
    ESP_LOGW(TAG, "heartbeat_failed reason=memory");
    cJSON_Delete(body);
    return;
  }
  char *payload = cJSON_PrintUnformatted(body);
  cJSON_Delete(body);
  if (payload == NULL) {
    ESP_LOGW(TAG, "heartbeat_failed reason=memory");
    return;
  }
  esp_http_client_config_t http_config = {
      .url = s_url,
      .timeout_ms = 5000,
      .disable_auto_redirect = true,
  };
  esp_http_client_handle_t client = esp_http_client_init(&http_config);
  if (client == NULL) {
    ESP_LOGW(TAG, "heartbeat_failed reason=client_init");
    cJSON_free(payload);
    return;
  }
  if (esp_http_client_set_method(client, HTTP_METHOD_POST) != ESP_OK ||
      esp_http_client_set_header(client, "Content-Type", "application/json") != ESP_OK ||
      esp_http_client_set_post_field(client, payload, (int)strlen(payload)) != ESP_OK) {
    ESP_LOGW(TAG, "heartbeat_failed reason=request_setup");
    esp_http_client_cleanup(client);
    cJSON_free(payload);
    return;
  }
  esp_err_t err = esp_http_client_perform(client);
  if (err == ESP_OK && esp_http_client_get_status_code(client) == 204) {
    ESP_LOGD(TAG, "heartbeat_accepted");
  } else if (err == ESP_OK) {
    ESP_LOGW(TAG, "heartbeat_failed http_status=%d", esp_http_client_get_status_code(client));
  } else {
    ESP_LOGW(TAG, "heartbeat_failed transport=%s", esp_err_to_name(err));
  }
  esp_http_client_cleanup(client);
  cJSON_free(payload);
}

static void heartbeat_task(void *arg) {
  (void)arg;
  for (;;) {
    send_heartbeat();
    vTaskDelay(pdMS_TO_TICKS(HEARTBEAT_INTERVAL_MS));
  }
}

esp_err_t heartbeat_start(const app_config_t *config) {
  if (config == NULL) {
    return ESP_ERR_INVALID_ARG;
  }
  if (config->backend_host == NULL || config->backend_host[0] == '\0') {
    ESP_LOGI(TAG, "heartbeat_disabled reason=no_backend_host");
    return ESP_OK;
  }
  if (!encode_device_url(s_url, sizeof(s_url), config)) {
    return ESP_ERR_INVALID_ARG;
  }
  s_config = *config;
  if (xTaskCreate(heartbeat_task, "iemp_heartbeat", 6144, NULL, 4, NULL) != pdPASS) {
    return ESP_ERR_NO_MEM;
  }
  ESP_LOGI(TAG, "heartbeat_started interval_ms=%d", HEARTBEAT_INTERVAL_MS);
  return ESP_OK;
}
