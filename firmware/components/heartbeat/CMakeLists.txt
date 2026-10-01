idf_component_register(SRCS "heartbeat.c" INCLUDE_DIRS "include"
                       REQUIRES app_config esp_http_client json
                       PRIV_REQUIRES freertos log)
