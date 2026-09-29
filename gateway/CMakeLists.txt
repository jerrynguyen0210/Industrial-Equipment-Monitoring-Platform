cmake_minimum_required(VERSION 3.16)
project(iemp_gateway VERSION 0.1.0 LANGUAGES CXX)

find_package(SQLite3 REQUIRED)
find_package(CURL REQUIRED)
find_package(Threads REQUIRED)
find_path(MOSQUITTO_INCLUDE_DIR mosquitto.h)
find_library(MOSQUITTO_LIBRARY mosquitto)
find_path(NLOHMANN_JSON_INCLUDE_DIR nlohmann/json.hpp)
if(NOT MOSQUITTO_INCLUDE_DIR OR NOT MOSQUITTO_LIBRARY OR NOT NLOHMANN_JSON_INCLUDE_DIR)
  message(FATAL_ERROR "Gateway requires libmosquitto and nlohmann JSON development headers")
endif()

add_executable(gateway
  src/main.cpp
  src/config.cpp
  src/log.cpp
  src/intake.cpp
  src/forwarder.cpp
  src/http/client.cpp
  src/mqtt/client.cpp
  src/telemetry/event.cpp
  src/sqlite/store.cpp
)
target_compile_features(gateway PRIVATE cxx_std_17)
set_target_properties(gateway PROPERTIES CXX_EXTENSIONS OFF)
target_include_directories(gateway PRIVATE include ${MOSQUITTO_INCLUDE_DIR} ${NLOHMANN_JSON_INCLUDE_DIR})
target_link_libraries(gateway PRIVATE SQLite::SQLite3 CURL::libcurl Threads::Threads ${MOSQUITTO_LIBRARY})

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(gateway PRIVATE -Wall -Wextra -Wpedantic -Wconversion -Werror)
endif()

include(CTest)
if(BUILD_TESTING)
  add_executable(gateway_store_test
    tests/test_store.cpp
    src/forwarder.cpp
    src/log.cpp
    src/sqlite/store.cpp
  )
  target_compile_features(gateway_store_test PRIVATE cxx_std_17)
  set_target_properties(gateway_store_test PROPERTIES CXX_EXTENSIONS OFF)
  target_include_directories(gateway_store_test PRIVATE include ${NLOHMANN_JSON_INCLUDE_DIR})
  target_link_libraries(gateway_store_test PRIVATE SQLite::SQLite3 Threads::Threads)
  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(gateway_store_test PRIVATE -Wall -Wextra -Wpedantic -Wconversion -Werror)
  endif()
  add_test(NAME gateway_store COMMAND gateway_store_test)

  find_package(Python3 COMPONENTS Interpreter REQUIRED)
  find_program(MOSQUITTO_BROKER_EXECUTABLE mosquitto)
  find_program(MOSQUITTO_PUB_EXECUTABLE mosquitto_pub)
  find_program(MOSQUITTO_PASSWD_EXECUTABLE mosquitto_passwd)
  if(NOT MOSQUITTO_BROKER_EXECUTABLE OR NOT MOSQUITTO_PUB_EXECUTABLE OR
     NOT MOSQUITTO_PASSWD_EXECUTABLE)
    message(FATAL_ERROR "Gateway intake tests require mosquitto and mosquitto-clients")
  endif()
  add_test(NAME gateway_lifecycle
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_gateway.py $<TARGET_FILE:gateway>)
  add_test(NAME gateway_mqtt_intake
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_mqtt.py
            $<TARGET_FILE:gateway> ${MOSQUITTO_BROKER_EXECUTABLE}
            ${MOSQUITTO_PUB_EXECUTABLE} ${MOSQUITTO_PASSWD_EXECUTABLE})
  add_test(NAME gateway_http_delivery
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_forwarder_http.py
            $<TARGET_FILE:gateway> ${MOSQUITTO_BROKER_EXECUTABLE}
            ${MOSQUITTO_PASSWD_EXECUTABLE})
endif()

install(TARGETS gateway RUNTIME DESTINATION bin)
