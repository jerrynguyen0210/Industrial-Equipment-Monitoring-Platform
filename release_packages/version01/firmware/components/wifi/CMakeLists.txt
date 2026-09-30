idf_component_register(SRCS "wifi_station.c" INCLUDE_DIRS "include"
                       REQUIRES app_config esp_wifi esp_event esp_netif esp_hw_support freertos log)
