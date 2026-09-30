#pragma once

#include <stdbool.h>
#include <stddef.h>

#define IEMP_TEMPERATURE_INPUT_MAX_LENGTH 47

// Parses one finite Celsius value from a bounded, non-null-terminated buffer.
// Accepts optional surrounding ASCII whitespace and the DS18B20 range.
bool temperature_input_parse(const char *text, size_t length, float *out_celsius);
