#include <assert.h>
#include <errno.h>
#include <math.h>
#include <stddef.h>
#include <string.h>

#include "temperature_input.h"

static void accepts(const char *text, float expected) {
  float value = NAN;
  assert(temperature_input_parse(text, strlen(text), &value));
  assert(fabsf(value - expected) < 0.0001f);
}

static void rejects(const char *text) {
  float value = 42.0f;
  assert(!temperature_input_parse(text, strlen(text), &value));
  assert(value == 42.0f);
}

int main(void) {
  accepts("-55", -55.0f);
  accepts("125", 125.0f);
  accepts("  23.75\r\n", 23.75f);
  accepts("0", 0.0f);
  accepts("1e2", 100.0f);
  accepts("\t-12.5 \v\f", -12.5f);
  errno = ERANGE;
  accepts("23.5", 23.5f);
  rejects("");
  rejects("   ");
  rejects("-55.01");
  rejects("125.01");
  rejects("nan");
  rejects("inf");
  rejects("-inf");
  rejects("1e999");
  rejects("1e-999");
  rejects("-1e-999");
  rejects("23 C");
  rejects("23;24");

  float value = 42.0f;
  const char embedded_zero[] = {'2', '3', '\0', '4'};
  assert(!temperature_input_parse(embedded_zero, sizeof(embedded_zero), &value));
  assert(value == 42.0f);
  assert(!temperature_input_parse(NULL, 1, &value));
  assert(!temperature_input_parse("23", 2, NULL));
  char overlong[48];
  memset(overlong, '1', sizeof(overlong));
  assert(!temperature_input_parse(overlong, sizeof(overlong), &value));
  char maximum_length[IEMP_TEMPERATURE_INPUT_MAX_LENGTH];
  memset(maximum_length, ' ', sizeof(maximum_length));
  memcpy(maximum_length, "23", 2);
  assert(temperature_input_parse(maximum_length, sizeof(maximum_length), &value));
  assert(value == 23.0f);
  return 0;
}
