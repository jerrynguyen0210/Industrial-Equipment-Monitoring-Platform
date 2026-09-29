#pragma once

#include <stdbool.h>
#include <stdint.h>

// 12 hexadecimal MAC digits, a separator, 16 hexadecimal counter digits, NUL.
#define IEMP_BOOT_ID_SIZE 30

typedef struct {
  char boot_id[IEMP_BOOT_ID_SIZE];
  uint64_t next_sequence;
} identity_t;

// The first event in every boot is sequence 0. These functions are intended for
// one event-creation task; callers must synchronize if they share the context.
bool identity_init(identity_t *identity, const char *boot_id);
bool identity_next_sequence(identity_t *identity, int64_t *sequence);
