#include "sampling.h"

#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sdkconfig.h"
#include "telemetry.h"
#include "temperature_sensor.h"

static const char *TAG = "sampling";

#if !CONFIG_IEMP_DEMO_SYNTHETIC_SENSOR
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
    telemetry_submit_temperature(demo_celsius);
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
      telemetry_submit_temperature(sample.celsius);
    } else {
      ESP_LOGW(TAG, "sensor_state=error reason=%s error=%s", status_reason(sample.status),
               esp_err_to_name(sample.driver_error));
    }
    vTaskDelayUntil(&last_wake, period);
  }
#endif
}

esp_err_t sampling_start(void) {
  return xTaskCreate(sampling_task, "temperature_sample", 4096, NULL, 4, NULL) == pdPASS
             ? ESP_OK
             : ESP_ERR_NO_MEM;
}
