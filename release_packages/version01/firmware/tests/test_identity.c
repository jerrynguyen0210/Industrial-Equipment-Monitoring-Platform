#include <assert.h>
#include <stdint.h>
#include <string.h>

#include "identity.h"

int main(void) {
  identity_t identity;
  int64_t sequence = -1;
  assert(!identity_init(NULL, "boot"));
  assert(!identity_init(&identity, ""));
  assert(identity_init(&identity, "mac-0000000000000001"));
  assert(identity.next_sequence == 0);
  assert(strcmp(identity.boot_id, "mac-0000000000000001") == 0);
  assert(identity_next_sequence(&identity, &sequence) && sequence == 0);
  assert(identity_next_sequence(&identity, &sequence) && sequence == 1);

  identity.next_sequence = INT64_MAX;
  assert(identity_next_sequence(&identity, &sequence) && sequence == INT64_MAX);
  assert(!identity_next_sequence(&identity, &sequence));
  assert(identity_init(&identity, "mac-0000000000000002"));
  assert(identity_next_sequence(&identity, &sequence) && sequence == 0);
  return 0;
}
