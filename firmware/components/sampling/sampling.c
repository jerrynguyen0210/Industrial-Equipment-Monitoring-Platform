#include "sampling.h"

#include <stdio.h>
#include <string.h>

#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sdkconfig.h"
#include "telemetry.h"
#include "temperature_input.h"
#include "temperature_sensor.h"

#if !CONFIG_IEMP_TEMPERATURE_DISABLED && !CONFIG_IEMP_WEB_SENSOR_INPUT
static const char *TAG = "sampling";
#endif

#if CONFIG_IEMP_DS18B20_SENSOR
static const char *status_reason(temperature_sample_status_t status) {
  switch (status) {
  case TEMPERATURE_SAMPLE_DISCONNECTED:
    return "disconnected";
  case TEMPERATURE_SAMPLE_CRC_ERROR:
    return "crc_error";
  case TEMPERATURE_SAMPLE_INVALID:
    return "invalid_reading";
  case TEMPERATURE_SAMPLE_IO_ERROR:
    return "io_error";
  case TEMPERATURE_SAMPLE_VALID:
    return "valid";
  }
  return "unknown";
}
#endif

#if CONFIG_IEMP_MANUAL_SENSOR_INPUT
static void publish_typed_temperature(const char *line) {
  float value;
  if (!temperature_input_parse(line, strlen(line), &value)) {
    ESP_LOGW(TAG, "sensor_input=rejected");
    return;
  }
  ESP_LOGI(TAG, "sensor_state=manual temperature_c=%.2f", (double)value);
  if (telemetry_submit_temperature(value) != ESP_OK) {
    ESP_LOGW(TAG, "sensor_input=not_queued");
  }
}

static void manual_input_task(void *arg) {
  (void)arg;
  char line[IEMP_TEMPERATURE_INPUT_MAX_LENGTH + 1];
  size_t used = 0;

  ESP_LOGI(TAG, "sensor_input=ready range_c=-55..125");
  fputs("\nEnter temperature in Celsius, then press Enter:\n> ", stdout);
  fflush(stdout);
  for (;;) {
    const int ch = fgetc(stdin);
    if (ch == EOF) {
      clearerr(stdin);
      vTaskDelay(pdMS_TO_TICKS(50));
      continue;
    }
    if (ch == '\r' || ch == '\n') {
      if (used == 0) {
        continue;
      }
      line[used] = '\0';
      used = 0;
      fputc('\n', stdout);
      fflush(stdout);
      publish_typed_temperature(line);
      fputs("> ", stdout);
      fflush(stdout);
      continue;
    }
    if (ch == '\b' || ch == 0x7f) {
      if (used > 0) {
        --used;
        fputs("\b \b", stdout);
        fflush(stdout);
      }
      continue;
    }
    if (ch < 32 || ch > 126 || used + 1 >= sizeof(line)) {
      continue;
    }
    line[used++] = (char)ch;
    fputc(ch, stdout);
    fflush(stdout);
  }
}
#endif

#if CONFIG_IEMP_DS18B20_SENSOR || CONFIG_IEMP_DEMO_SYNTHETIC_SENSOR
static void sampling_task(void *arg) {
  (void)arg;
  const TickType_t period = pdMS_TO_TICKS(CONFIG_IEMP_SAMPLE_INTERVAL_MS);
  TickType_t last_wake = xTaskGetTickCount();
#if CONFIG_IEMP_DEMO_SYNTHETIC_SENSOR
  const float demo_celsius = CONFIG_IEMP_DEMO_TEMPERATURE_CENTICELSIUS / 100.0f;
  ESP_LOGW(TAG, "sensor_state=synthetic_demo temperature_c=%.2f interval_ms=%d",
           (double)demo_celsius, CONFIG_IEMP_SAMPLE_INTERVAL_MS);
  for (;;) {
    ESP_LOGI(TAG, "sensor_state=synthetic_demo temperature_c=%.2f", (double)demo_celsius);
    if (telemetry_submit_temperature(demo_celsius) != ESP_OK) {
      ESP_LOGW(TAG, "sensor_input=not_queued");
    }
    vTaskDelayUntil(&last_wake, period);
  }
#else
  temperature_sensor_t *sensor = NULL;

  ESP_LOGI(TAG, "sensor_state=starting model=DS18B20 gpio=%d interval_ms=%d",
           CONFIG_IEMP_SENSOR_GPIO, CONFIG_IEMP_SAMPLE_INTERVAL_MS);
  for (;;) {
    if (sensor == NULL) {
      esp_err_t err = temperature_sensor_create(CONFIG_IEMP_SENSOR_GPIO, &sensor);
      if (err != ESP_OK) {
        ESP_LOGE(TAG, "sensor_state=error reason=driver_init error=%s", esp_err_to_name(err));
        vTaskDelayUntil(&last_wake, period);
        continue;
      }
    }

    temperature_sample_t sample = temperature_sensor_read(sensor);
    if (sample.status == TEMPERATURE_SAMPLE_VALID) {
      ESP_LOGI(TAG, "sensor_state=valid temperature_c=%.4f", (double)sample.celsius);
      if (telemetry_submit_temperature(sample.celsius) != ESP_OK) {
        ESP_LOGW(TAG, "sensor_input=not_queued");
      }
    } else {
      ESP_LOGW(TAG, "sensor_state=error reason=%s error=%s", status_reason(sample.status),
               esp_err_to_name(sample.driver_error));
    }
    vTaskDelayUntil(&last_wake, period);
  }
#endif
}
#endif

esp_err_t sampling_start(void) {
#if CONFIG_IEMP_TEMPERATURE_DISABLED || CONFIG_IEMP_WEB_SENSOR_INPUT
  return ESP_ERR_NOT_SUPPORTED;
#else
#if CONFIG_IEMP_MANUAL_SENSOR_INPUT
  const BaseType_t created = xTaskCreate(manual_input_task, "sensor_input", 4096, NULL, 4, NULL);
#else
  const BaseType_t created = xTaskCreate(sampling_task, "temperature_sample", 4096, NULL, 4, NULL);
#endif
  return created == pdPASS ? ESP_OK : ESP_ERR_NO_MEM;
#endif
}
