#include "web_input.h"

#include <stdbool.h>
#include <stddef.h>
#include <string.h>

#include "esp_http_server.h"
#include "esp_log.h"
#include "telemetry.h"
#include "temperature_input.h"

#define WEB_INPUT_MAX_KEY 63

static const char *TAG = "web_input";
static httpd_handle_t s_server;
static const char *s_key;

static const char PAGE[] =
    "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
    "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
    "<title>ESP32 temperature input</title>"
    "<style>body{font:16px system-ui,sans-serif;max-width:28rem;margin:3rem auto;"
    "padding:0 1rem;color:#18202a}label{display:block;margin:1rem 0 .35rem}"
    "input,button{box-sizing:border-box;width:100%;padding:.7rem;font:inherit}"
    "button{margin-top:1.3rem;cursor:pointer}#result{min-height:1.5rem}</style>"
    "</head><body><main><h1>Temperature input</h1>"
    "<p>Enter one Celsius reading. Each submission queues one MQTT event.</p>"
    "<form id=\"entry\"><label for=\"value\">Temperature (&deg;C)</label>"
    "<input id=\"value\" type=\"number\" step=\"any\" min=\"-55\" max=\"125\" required>"
    "<label for=\"key\">Device input key</label>"
    "<input id=\"key\" type=\"password\" autocomplete=\"off\" required>"
    "<button type=\"submit\">Submit reading</button></form>"
    "<p id=\"result\" role=\"status\" aria-live=\"polite\"></p></main>"
    "<script>document.getElementById('entry').addEventListener('submit',async e=>{"
    "e.preventDefault();const form=e.currentTarget;const button=form.querySelector('button');"
    "const result=document.getElementById('result');button.disabled=true;"
    "result.textContent='Submitting...';try{const response=await fetch('/temperature',{"
    "method:'POST',headers:{'Content-Type':'text/plain','X-Temperature-Key':"
    "document.getElementById('key').value},body:document.getElementById('value').value,"
    "credentials:'omit'});if(response.ok){result.textContent='Reading queued for MQTT delivery.';"
    "document.getElementById('value').value='';}else{result.textContent="
    "response.status===401?'Incorrect device input key.':"
    "response.status===400?'Enter a Celsius value from -55 to 125.':"
    "response.status===503?'Queue unavailable; try again later.':"
    "'Submission failed ('+response.status+').';}}catch(_){"
    "result.textContent='Connection lost; check the ESP32 Wi-Fi address.';}"
    "finally{button.disabled=false;}});</script></body></html>";

static esp_err_t page_handler(httpd_req_t *request) {
  esp_err_t err = httpd_resp_set_type(request, "text/html; charset=utf-8");
  if (err != ESP_OK) {
    return err;
  }
  err = httpd_resp_set_hdr(request, "Cache-Control", "no-store");
  if (err != ESP_OK) {
    return err;
  }
  err = httpd_resp_set_hdr(request, "X-Content-Type-Options", "nosniff");
  if (err != ESP_OK) {
    return err;
  }
  err = httpd_resp_set_hdr(request, "Content-Security-Policy",
                           "default-src 'none'; style-src 'unsafe-inline'; "
                           "script-src 'unsafe-inline'; connect-src 'self'; form-action 'self'");
  if (err != ESP_OK) {
    return err;
  }
  return httpd_resp_send(request, PAGE, HTTPD_RESP_USE_STRLEN);
}

static bool key_matches(httpd_req_t *request) {
  const size_t expected_length = strlen(s_key);
  const size_t supplied_length = httpd_req_get_hdr_value_len(request, "X-Temperature-Key");
  if (supplied_length != expected_length || supplied_length > WEB_INPUT_MAX_KEY) {
    return false;
  }

  char supplied[WEB_INPUT_MAX_KEY + 1];
  if (httpd_req_get_hdr_value_str(request, "X-Temperature-Key", supplied, sizeof(supplied)) !=
      ESP_OK) {
    return false;
  }
  unsigned char difference = 0;
  for (size_t index = 0; index < expected_length; ++index) {
    difference |= (unsigned char)(supplied[index] ^ s_key[index]);
  }
  return difference == 0;
}

static esp_err_t temperature_handler(httpd_req_t *request) {
  if (!key_matches(request)) {
    return httpd_resp_send_err(request, HTTPD_401_UNAUTHORIZED, "Incorrect input key");
  }
  if (request->content_len <= 0 || request->content_len > IEMP_TEMPERATURE_INPUT_MAX_LENGTH) {
    return httpd_resp_send_err(request, HTTPD_400_BAD_REQUEST, "Invalid temperature length");
  }

  char body[IEMP_TEMPERATURE_INPUT_MAX_LENGTH];
  size_t received = 0;
  const size_t expected = (size_t)request->content_len;
  while (received < expected) {
    const int count = httpd_req_recv(request, body + received, expected - received);
    if (count <= 0) {
      return httpd_resp_send_err(request, HTTPD_408_REQ_TIMEOUT, "Incomplete request");
    }
    received += (size_t)count;
  }

  float celsius;
  if (!temperature_input_parse(body, received, &celsius)) {
    return httpd_resp_send_err(request, HTTPD_400_BAD_REQUEST, "Expected -55 to 125 Celsius");
  }
  if (telemetry_submit_temperature(celsius) != ESP_OK) {
    esp_err_t err = httpd_resp_set_status(request, "503 Service Unavailable");
    if (err != ESP_OK) {
      return err;
    }
    err = httpd_resp_set_type(request, "text/plain; charset=utf-8");
    if (err != ESP_OK) {
      return err;
    }
    return httpd_resp_sendstr(request, "Telemetry queue unavailable");
  }

  ESP_LOGI(TAG, "sensor_state=web_manual temperature_c=%.2f", (double)celsius);
  esp_err_t err = httpd_resp_set_type(request, "application/json");
  if (err != ESP_OK) {
    return err;
  }
  err = httpd_resp_set_hdr(request, "Cache-Control", "no-store");
  if (err != ESP_OK) {
    return err;
  }
  return httpd_resp_sendstr(request, "{\"status\":\"queued\"}");
}

esp_err_t web_input_start(const app_config_t *config) {
  if (config == NULL || config->web_input_key == NULL || s_server != NULL) {
    return ESP_ERR_INVALID_ARG;
  }
  s_key = config->web_input_key;
  httpd_config_t http_config = HTTPD_DEFAULT_CONFIG();
  esp_err_t err = httpd_start(&s_server, &http_config);
  if (err != ESP_OK) {
    return err;
  }

  const httpd_uri_t page = {.uri = "/", .method = HTTP_GET, .handler = page_handler};
  const httpd_uri_t temperature = {
      .uri = "/temperature", .method = HTTP_POST, .handler = temperature_handler};
  err = httpd_register_uri_handler(s_server, &page);
  if (err == ESP_OK) {
    err = httpd_register_uri_handler(s_server, &temperature);
  }
  if (err != ESP_OK) {
    httpd_stop(s_server);
    s_server = NULL;
    return err;
  }
  ESP_LOGI(TAG, "web_input=ready port=%u", (unsigned)http_config.server_port);
  return ESP_OK;
}
