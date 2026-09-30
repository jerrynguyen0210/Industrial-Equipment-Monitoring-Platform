idf_component_register(SRCS "telemetry.c" "telemetry_encoding.c" INCLUDE_DIRS "include"
                       REQUIRES app_config identity esp_timer mqtt esp_netif
                       PRIV_REQUIRES freertos log esp_event)
