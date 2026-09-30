#include <assert.h>
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
  rejects("");
  rejects("   ");
  rejects("-55.01");
  rejects("125.01");
  rejects("nan");
  rejects("inf");
  rejects("23 C");
  rejects("23;24");

  float value = 42.0f;
  const char embedded_zero[] = {'2', '3', '\0', '4'};
  assert(!temperature_input_parse(embedded_zero, sizeof(embedded_zero), &value));
  assert(!temperature_input_parse(NULL, 1, &value));
  assert(!temperature_input_parse("23", 2, NULL));
  char overlong[48];
  memset(overlong, '1', sizeof(overlong));
  assert(!temperature_input_parse(overlong, sizeof(overlong), &value));
  return 0;
}
