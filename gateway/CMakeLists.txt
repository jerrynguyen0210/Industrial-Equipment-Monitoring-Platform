cmake_minimum_required(VERSION 3.16)
project(iemp_gateway VERSION 0.1.0 LANGUAGES CXX)

find_package(SQLite3 REQUIRED)
find_package(Threads REQUIRED)

add_executable(gateway
  src/main.cpp
  src/config.cpp
  src/log.cpp
  src/sqlite/store.cpp
)
target_compile_features(gateway PRIVATE cxx_std_17)
set_target_properties(gateway PROPERTIES CXX_EXTENSIONS OFF)
target_include_directories(gateway PRIVATE include)
target_link_libraries(gateway PRIVATE SQLite::SQLite3 Threads::Threads)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(gateway PRIVATE -Wall -Wextra -Wpedantic -Wconversion -Werror)
endif()

include(CTest)
if(BUILD_TESTING)
  find_package(Python3 COMPONENTS Interpreter REQUIRED)
  add_test(NAME gateway_lifecycle
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_gateway.py $<TARGET_FILE:gateway>)
endif()

install(TARGETS gateway RUNTIME DESTINATION bin)
