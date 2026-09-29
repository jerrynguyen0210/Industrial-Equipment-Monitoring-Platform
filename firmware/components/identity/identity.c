#include "identity.h"

#include <limits.h>
#include <string.h>

bool identity_init(identity_t *identity, const char *boot_id) {
  if (identity == NULL || boot_id == NULL) {
    return false;
  }
  const size_t length = strlen(boot_id);
  if (length == 0 || length >= IEMP_BOOT_ID_SIZE) {
    return false;
  }
  memcpy(identity->boot_id, boot_id, length + 1);
  identity->next_sequence = 0;
  return true;
}

bool identity_next_sequence(identity_t *identity, int64_t *sequence) {
  if (identity == NULL || sequence == NULL || identity->next_sequence > INT64_MAX) {
    return false;
  }
  *sequence = (int64_t)identity->next_sequence;
  ++identity->next_sequence;
  return true;
}
