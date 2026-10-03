#include "temperature_input.h"

#include <ctype.h>
#include <errno.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

bool temperature_input_parse(const char *text, size_t length, float *out_celsius) {
  if (text == NULL || out_celsius == NULL || length == 0 ||
      length > IEMP_TEMPERATURE_INPUT_MAX_LENGTH || memchr(text, '\0', length) != NULL) {
    return false;
  }

  char buffer[IEMP_TEMPERATURE_INPUT_MAX_LENGTH + 1];
  memcpy(buffer, text, length);
  buffer[length] = '\0';

  char *end = NULL;
  errno = 0;
  const float value = strtof(buffer, &end);
  // Underflow can produce a finite zero; do not accept it as a real reading.
  if (end == buffer || errno == ERANGE) {
    return false;
  }
  while (*end != '\0' && isspace((unsigned char)*end)) {
    ++end;
  }
  if (*end != '\0' || !isfinite(value) || value < -55.0f || value > 125.0f) {
    return false;
  }

  *out_celsius = value;
  return true;
}
