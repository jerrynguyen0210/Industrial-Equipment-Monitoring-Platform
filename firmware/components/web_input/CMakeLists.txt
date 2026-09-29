idf_component_register(SRCS "web_input.c" INCLUDE_DIRS "include"
                       REQUIRES app_config telemetry temperature_input esp_http_server
                       PRIV_REQUIRES log)
