#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include "boot_id.h"
#include "esp_mac.h"
#include "nvs.h"

static uint64_t persisted_counter;
static uint64_t staged_counter;
static bool has_counter;
static bool fail_commit;

esp_err_t esp_efuse_mac_get_default(uint8_t mac[6]) {
  const uint8_t factory_mac[6] = {0xaa, 0xbb, 0xcc, 0xdd, 0xee, 0xff};
  memcpy(mac, factory_mac, sizeof(factory_mac));
  return ESP_OK;
}

esp_err_t nvs_open(const char *name, int open_mode, nvs_handle_t *handle) {
  assert(strcmp(name, "iemp_boot") == 0);
  assert(open_mode == NVS_READWRITE);
  *handle = 1;
  return ESP_OK;
}

esp_err_t nvs_get_u64(nvs_handle_t handle, const char *key, uint64_t *value) {
  assert(handle == 1 && strcmp(key, "counter") == 0);
  if (!has_counter) {
    return ESP_ERR_NVS_NOT_FOUND;
  }
  *value = persisted_counter;
  return ESP_OK;
}

esp_err_t nvs_set_u64(nvs_handle_t handle, const char *key, uint64_t value) {
  assert(handle == 1 && strcmp(key, "counter") == 0);
  staged_counter = value;
  return ESP_OK;
}

esp_err_t nvs_commit(nvs_handle_t handle) {
  assert(handle == 1);
  if (fail_commit) {
    return ESP_FAIL;
  }
  persisted_counter = staged_counter;
  has_counter = true;
  return ESP_OK;
}

void nvs_close(nvs_handle_t handle) { assert(handle == 1); }

int main(void) {
  char first[IEMP_BOOT_ID_SIZE];
  char second[IEMP_BOOT_ID_SIZE];
  assert(boot_id_create(first) == ESP_OK);
  assert(strcmp(first, "aabbccddeeff-0000000000000001") == 0);
  assert(boot_id_create(second) == ESP_OK);
  assert(strcmp(second, "aabbccddeeff-0000000000000002") == 0);
  assert(strcmp(first, second) != 0);

  fail_commit = true;
  assert(boot_id_create(second) == ESP_FAIL);
  assert(persisted_counter == 2);
  fail_commit = false;
  assert(boot_id_create(second) == ESP_OK);
  assert(strcmp(second, "aabbccddeeff-0000000000000003") == 0);

  persisted_counter = UINT64_MAX;
  assert(boot_id_create(second) == ESP_ERR_INVALID_STATE);
  return 0;
}
