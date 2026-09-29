#include "telemetry.h"

#include <inttypes.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <sys/time.h>
#include <time.h>

#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif_sntp.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "mqtt_client.h"
#include "telemetry_encoding.h"

#define TELEMETRY_QUEUE_LENGTH 32
#define MQTT_ACK_RETRY_MS 20000

typedef struct {
  int64_t sequence_number;
  int64_t device_uptime_ms;
  float celsius;
  char measured_at[32];
} queued_reading_t;

typedef enum { SIGNAL_CONNECTED, SIGNAL_DISCONNECTED, SIGNAL_PUBLISHED } signal_type_t;
typedef struct {
  signal_type_t type;
  int message_id;
} mqtt_signal_t;

static const char *TAG = "telemetry";
static QueueHandle_t s_readings;
static QueueHandle_t s_signals;
static identity_t *s_identity;
static app_config_t s_config;
static esp_mqtt_client_handle_t s_client;
static char s_topic[sizeof("equipment//telemetry") + 128];
static atomic_bool s_clock_synchronised = ATOMIC_VAR_INIT(false);

static void on_time_sync(struct timeval *time_value) {
  (void)time_value;
  atomic_store(&s_clock_synchronised, true);
  ESP_LOGI(TAG, "clock_state=synchronised");
}

static void on_mqtt_event(void *arg, esp_event_base_t base, int32_t event_id, void *data) {
  (void)arg;
  (void)base;
  esp_mqtt_event_handle_t event = data;
  mqtt_signal_t signal;
  switch (event_id) {
  case MQTT_EVENT_CONNECTED:
    signal = (mqtt_signal_t){.type = SIGNAL_CONNECTED};
    break;
  case MQTT_EVENT_DISCONNECTED:
    signal = (mqtt_signal_t){.type = SIGNAL_DISCONNECTED};
    break;
  case MQTT_EVENT_PUBLISHED:
    signal = (mqtt_signal_t){.type = SIGNAL_PUBLISHED, .message_id = event->msg_id};
    break;
  default:
    return;
  }
  if (xQueueSend(s_signals, &signal, 0) != pdTRUE) {
    ESP_LOGE(TAG, "mqtt_signal_dropped type=%d", (int)signal.type);
  }
}

static void publisher_task(void *arg) {
  const app_config_t *config = arg;
  queued_reading_t pending = {0};
  char payload[768];
  bool connected = false;
  bool have_pending = false;
  int outstanding = -1;
  TickType_t sent_at = 0;
  mqtt_signal_t signal;

  for (;;) {
    if (xQueueReceive(s_signals, &signal, pdMS_TO_TICKS(100)) == pdTRUE) {
      do {
        if (signal.type == SIGNAL_CONNECTED) {
          connected = true;
          outstanding = -1;
          ESP_LOGI(TAG, "mqtt_state=connected");
        } else if (signal.type == SIGNAL_DISCONNECTED) {
          connected = false;
          outstanding = -1;
          ESP_LOGW(TAG, "mqtt_state=disconnected");
        } else if (have_pending && outstanding == signal.message_id) {
          ESP_LOGI(TAG, "telemetry_acked sequence_number=%" PRId64, pending.sequence_number);
          have_pending = false;
          outstanding = -1;
        }
      } while (xQueueReceive(s_signals, &signal, 0) == pdTRUE);
    }

    if (!have_pending && xQueueReceive(s_readings, &pending, 0) == pdTRUE) {
      telemetry_event_t event = {
          .device_id = config->device_id,
          .boot_id = s_identity->boot_id,
          .sequence_number = pending.sequence_number,
          .device_uptime_ms = pending.device_uptime_ms,
          .celsius = pending.celsius,
          .measured_at = pending.measured_at,
      };
      if (!telemetry_encode(&event, payload, sizeof(payload))) {
        ESP_LOGE(TAG, "telemetry_dropped reason=encode sequence_number=%" PRId64,
                 pending.sequence_number);
      } else {
        have_pending = true;
      }
    }

    if (connected && have_pending && outstanding >= 0 &&
        (TickType_t)(xTaskGetTickCount() - sent_at) >= pdMS_TO_TICKS(MQTT_ACK_RETRY_MS)) {
      ESP_LOGW(TAG, "telemetry_retry reason=ack_timeout sequence_number=%" PRId64,
               pending.sequence_number);
      outstanding = -1;
    }
    if (connected && have_pending && outstanding < 0) {
      int message_id =
          esp_mqtt_client_enqueue(s_client, s_topic, payload, (int)strlen(payload), 1, 0, true);
      if (message_id >= 0) {
        outstanding = message_id;
        sent_at = xTaskGetTickCount();
      } else {
        ESP_LOGW(TAG, "telemetry_retry reason=enqueue_failed sequence_number=%" PRId64,
                 pending.sequence_number);
      }
    }
  }
}

esp_err_t telemetry_start(const app_config_t *config, identity_t *identity) {
  if (config == NULL || identity == NULL) {
    return ESP_ERR_INVALID_ARG;
  }
  int written = snprintf(s_topic, sizeof(s_topic), "equipment/%s/telemetry", config->device_id);
  if (written < 0 || (size_t)written >= sizeof(s_topic)) {
    return ESP_ERR_INVALID_ARG;
  }
  s_identity = identity;
  s_config = *config;
  esp_err_t err;
  s_readings = xQueueCreate(TELEMETRY_QUEUE_LENGTH, sizeof(queued_reading_t));
  s_signals = xQueueCreate(8, sizeof(mqtt_signal_t));
  if (s_readings == NULL || s_signals == NULL) {
    err = ESP_ERR_NO_MEM;
    goto fail;
  }

  esp_sntp_config_t clock_config = ESP_NETIF_SNTP_DEFAULT_CONFIG("pool.ntp.org");
  clock_config.sync_cb = on_time_sync;
  err = esp_netif_sntp_init(&clock_config);
  bool clock_started = err == ESP_OK;
  if (err != ESP_OK) {
    ESP_LOGW(TAG, "clock_state=unsynchronised error=%s", esp_err_to_name(err));
  }

  esp_mqtt_client_config_t mqtt_config = {
      .broker.address.hostname = config->mqtt_host,
      .broker.address.port = config->mqtt_port,
      .broker.address.transport = MQTT_TRANSPORT_OVER_TCP,
      .credentials.client_id = config->device_id,
      .credentials.username = config->device_id,
      .credentials.authentication.password = config->mqtt_password,
  };
  s_client = esp_mqtt_client_init(&mqtt_config);
  if (s_client == NULL) {
    err = ESP_ERR_NO_MEM;
    goto fail_clock;
  }
  err = esp_mqtt_client_register_event(s_client, ESP_EVENT_ANY_ID, on_mqtt_event, NULL);
  if (err != ESP_OK) {
    goto fail_client;
  }
  err = esp_mqtt_client_start(s_client);
  if (err != ESP_OK) {
    goto fail_client;
  }
  if (xTaskCreate(publisher_task, "telemetry_publish", 6144, &s_config, 4, NULL) != pdPASS) {
    esp_mqtt_client_stop(s_client);
    err = ESP_ERR_NO_MEM;
    goto fail_client;
  }
  ESP_LOGI(TAG, "mqtt_state=starting topic=%s qos=1 queue_capacity=%d", s_topic,
           TELEMETRY_QUEUE_LENGTH);
  return ESP_OK;

fail_client:
  esp_mqtt_client_destroy(s_client);
  s_client = NULL;
fail_clock:
  if (clock_started) {
    esp_netif_sntp_deinit();
  }
fail:
  if (s_signals != NULL) {
    vQueueDelete(s_signals);
    s_signals = NULL;
  }
  if (s_readings != NULL) {
    vQueueDelete(s_readings);
    s_readings = NULL;
  }
  s_identity = NULL;
  return err;
}

void telemetry_submit_temperature(float celsius) {
  if (s_readings == NULL || s_identity == NULL) {
    return;
  }
  queued_reading_t reading = {.celsius = celsius, .device_uptime_ms = esp_timer_get_time() / 1000};
  if (!identity_next_sequence(s_identity, &reading.sequence_number)) {
    ESP_LOGE(TAG, "telemetry_dropped reason=sequence_exhausted");
    return;
  }
  if (atomic_load(&s_clock_synchronised)) {
    struct timeval now;
    struct tm utc;
    if (gettimeofday(&now, NULL) == 0 && gmtime_r(&now.tv_sec, &utc) != NULL &&
        utc.tm_year >= 120 && utc.tm_year <= 8099) {
      int written =
          snprintf(reading.measured_at, sizeof(reading.measured_at),
                   "%04d-%02d-%02dT%02d:%02d:%02d.%03ldZ", utc.tm_year + 1900, utc.tm_mon + 1,
                   utc.tm_mday, utc.tm_hour, utc.tm_min, utc.tm_sec, now.tv_usec / 1000);
      if (written < 0 || (size_t)written >= sizeof(reading.measured_at)) {
        reading.measured_at[0] = '\0';
      }
    }
  }
  if (xQueueSend(s_readings, &reading, 0) != pdTRUE) {
    ESP_LOGW(TAG, "telemetry_dropped reason=queue_full sequence_number=%" PRId64,
             reading.sequence_number);
  }
}
