# ESP32 firmware startup project

This ESP-IDF 5.5 project targets an ESP32-DevKitC-compatible board with a
standard ESP32, onboard flash, and a USB serial connection. It validates local
configuration, commits a new boot identity to NVS, starts a sequence counter at
zero, and joins a WPA2/WPA3 Wi-Fi network. It does not sample a sensor or publish
MQTT telemetry yet. There are no external sensor pins or wiring in this stage.

## Layout

| Path | Responsibility |
| --- | --- |
| `main/` | Startup order and identity/state logging. |
| `components/app_config/` | Kconfig options and validation. |
| `components/identity/` | Persistent boot ID and per-boot event sequence. |
| `components/wifi/` | Wi-Fi station setup and connection state logs. |
| `tests/` | Host tests for boot IDs, NVS commit failure, and sequences. |

## Configure, build, and flash

Install [ESP-IDF 5.5](https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32/get-started/index.html)
for ESP32 and activate its environment. From `firmware/`:

```sh
idf.py menuconfig
idf.py build
idf.py -p /dev/ttyUSB0 flash monitor
```

Under **Industrial Equipment Monitoring firmware**, set a registered device ID,
the 2.4 GHz Wi-Fi SSID, and its WPA2/WPA3 passphrase. The device ID must be one
MQTT topic level, 1–128 bytes, with no `/`, `+`, `#`, or control characters. The
SSID must be 1–32 bytes and the passphrase 8–63 bytes. The checked-in
`sdkconfig.defaults` only sets the ESP32 target. `idf.py menuconfig` writes the
values to `sdkconfig`, which is ignored by Git. Keep the generated firmware image
private: compile-time credentials are embedded in it. The Wi-Fi driver uses RAM
configuration rather than copying those credentials into NVS.

Without a host ESP-IDF install, use the pinned official container from
`firmware/` for both configuration and build:

```sh
docker run --rm -it -v "$PWD:/project" -w /project -u "$(id -u):$(id -g)" \
  -e HOME=/tmp espressif/idf:v5.5 idf.py menuconfig
docker run --rm -v "$PWD:/project" -w /project -u "$(id -u):$(id -g)" \
  -e HOME=/tmp espressif/idf:v5.5 idf.py build
```

An empty local configuration still compiles, but startup logs
`invalid_config field=...` and does not start Wi-Fi. A boot ID is still issued.
No example credentials are
shipped. To reset a local configuration, remove `sdkconfig` and run menuconfig
again. Do **not** erase NVS to fix a configuration error.

## Startup and identity

Startup creates a boot ID before validating Wi-Fi configuration. The ID has the form
`<factory MAC hex>-<16-digit NVS boot counter hex>`; the counter is incremented
and committed before the ID is logged. This gives a different ID on each normal
reboot of the same board. NVS initialization or commit failures stop startup
without erasing identity state. Erasing the NVS partition or replacing the board
resets the counter and breaks that continuity, so preserve NVS during updates.

The event sequence starts at **0** on every boot and can issue values through
`INT64_MAX`. The next allocation then fails; it never wraps. Wi-Fi reconnects
do not change either identity. The identity context remains in RAM for future
event creation. No event is allocated by the current startup-only firmware.

Serial output should contain `identity_ready boot_id=... sequence_next=0`,
`config_ready device_id=...`, then `state=starting`, `state=connecting`, and finally
`state=connected ip=...` after DHCP. It also includes the reset reason and
firmware version. Check two resets: the boot ID counter should advance and
`sequence_next` should again be zero. A disconnected station retries after a
jittered delay that grows from 0.5–1 second to at most 30 seconds and resets
after DHCP succeeds. The code never logs the passphrase.

## Host check and hardware validation

From the repository root, the identity test needs only a C11 compiler:

```sh
gcc -std=c11 -Wall -Wextra -Werror -pedantic \
  -I firmware/components/identity/include \
  firmware/components/identity/identity.c firmware/tests/test_identity.c \
  -o /tmp/iemp-firmware-test-identity
/tmp/iemp-firmware-test-identity
gcc -std=c11 -Wall -Wextra -Werror -pedantic \
  -I firmware/tests/stubs -I firmware/components/identity/include \
  firmware/components/identity/boot_id.c firmware/tests/test_boot_id.c \
  -o /tmp/iemp-firmware-test-boot-id
/tmp/iemp-firmware-test-boot-id
```

Hardware validation requires a board, USB serial access, and valid Wi-Fi
credentials. Record the board revision, ESP-IDF version, firmware commit, serial
port, and two boot logs when checking the reset and Wi-Fi acceptance criteria.
See [Firmware Coding Conventions](CODING_CONVENTIONS.md) for future sensor and
telemetry work.
