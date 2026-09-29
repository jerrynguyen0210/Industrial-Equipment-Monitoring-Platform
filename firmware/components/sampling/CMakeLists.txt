idf_component_register(SRCS "sampling.c" INCLUDE_DIRS "include"
                       REQUIRES temperature_sensor telemetry temperature_input PRIV_REQUIRES freertos log)
