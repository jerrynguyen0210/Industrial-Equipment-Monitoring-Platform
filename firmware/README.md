# ESP32 firmware startup project

This ESP-IDF 5.5 project targets an ESP32-DevKitC-compatible board with a
standard ESP32, onboard flash, and a USB serial connection. It validates local
configuration, commits a new boot identity to NVS, starts a sequence counter at
zero, joins a WPA2/WPA3 Wi-Fi network, and samples one DS18B20 temperature probe.
The probe is not installed yet. Until it is wired, normal mode logs an explicit
sensor error every sample period. An opt-in demo mode publishes a fixed synthetic
temperature for a board without the probe.

## Layout

| Path | Responsibility |
| --- | --- |
| `main/` | Startup order and identity/state logging. |
| `components/app_config/` | Kconfig options and validation. |
| `components/identity/` | Persistent boot ID and per-boot event sequence. |
| `components/wifi/` | Wi-Fi station setup and connection state logs. |
| `components/temperature_sensor/` | DS18B20 and 1-Wire integration, value validation. |
| `components/sampling/` | Periodic reads and valid/error serial logs. |
| `components/telemetry/` | Schema v1 JSON, clock quality, queue, and MQTT publisher. |
| `tests/` | Host tests for boot IDs, sequences, and sensor error handling. |

## Configure, build, and flash

Install [ESP-IDF 5.5.4](https://docs.espressif.com/projects/esp-idf/en/v5.5.4/esp32/get-started/index.html)
for ESP32 and activate its environment. From `firmware/`:

```sh
idf.py menuconfig
idf.py build
idf.py -p /dev/ttyUSB0 flash monitor
```

Under **Industrial Equipment Monitoring firmware**, set a registered device ID,
the 2.4 GHz Wi-Fi SSID, its WPA2/WPA3 passphrase, the broker's LAN address, and
the device-specific MQTT password. The MQTT username is the device ID. Provision
the account and write ACL using [the topic contract](../docs/mqtt-topic-contract.md).
The device ID must be one MQTT topic level, 1–128 bytes, with no `/`, `+`, `#`,
or control characters. The
SSID must be 1–32 bytes and the passphrase 8–63 bytes. The checked-in
`sdkconfig.defaults` only sets the ESP32 target. `idf.py menuconfig` writes the
values to `sdkconfig`, which is ignored by Git. Keep the generated firmware image
private: compile-time credentials are embedded in it. The Wi-Fi driver uses RAM
configuration rather than copying those credentials into NVS. The local Mosquitto
port defaults to 1883. Set `MQTT_BIND_ADDRESS` to the broker host's LAN address
for a real ESP32; `localhost` on the board does not reach the Compose broker.
The local MQTT listener is unencrypted and suitable only for a trusted lab LAN.

The **DS18B20 1-Wire data GPIO** defaults to GPIO 4 and the **Temperature sampling
interval** defaults to 5000 ms. Sampling runs independently of Wi-Fi, so sensor
state is logged even when Wi-Fi configuration is absent. The ESP-IDF component
manager downloads pinned versions of
[Espressif's DS18B20 driver](https://components.espressif.com/components/espressif/ds18b20/versions/0.4.0/readme)
and [1-Wire bus driver](https://components.espressif.com/components/espressif/onewire_bus/versions/1.1.0/readme)
on the first build.

For the current unwired board, enable **Demo-only synthetic temperature** in
`idf.py menuconfig` and set **Demo temperature** (default `2500`, meaning 25.00°C).
This publishes one constant event every five seconds without starting the sensor
driver. Serial logs say `sensor_state=synthetic_demo`. Use a dedicated demo device
ID and registered broker account: the frozen telemetry JSON has no synthetic
provenance field, so gateway and dashboard consumers see a `valid` temperature.
Disable the mode and wire the DS18B20 before using readings as physical evidence.

Without a host ESP-IDF install, use the pinned official container from
`firmware/` for both configuration and build:

```sh
docker run --rm -it -v "$PWD:/project" -w /project -u "$(id -u):$(id -g)" \
  -e HOME=/tmp espressif/idf:v5.5.4 idf.py menuconfig
docker run --rm -v "$PWD:/project" -w /project -u "$(id -u):$(id -g)" \
  -e HOME=/tmp espressif/idf:v5.5.4 idf.py build
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
do not change either identity. Every valid sensor reading allocates one sequence.
A full queue can cause a logged sequence gap; a reconnect does not reset it.

Serial output should contain `identity_ready boot_id=... sequence_next=0`,
`config_ready device_id=...`, then `state=starting`, `state=connecting`, and finally
`state=connected ip=...` after DHCP. It also includes the reset reason and
firmware version. Check two resets: the boot ID counter should advance and
`sequence_next` should again be zero. A disconnected station retries after a
jittered delay that grows from 0.5–1 second to at most 30 seconds and resets
after DHCP succeeds. The code never logs the passphrase.

## Temperature probe setup and behavior

This stage targets **one externally powered DS18B20** on an ESP32-DevKitC-compatible
board. Connect sensor VDD to **3.3 V**, GND to GND, and DQ to the configured GPIO
(GPIO 4 by default). Fit a **4.7 kΩ pull-up resistor** from DQ to 3.3 V, unless the
probe module already includes one. Do not pull the ESP32 data pin to 5 V.
Parasitic-power wiring and multiple probes on one bus are not supported by this
configuration. [The DS18B20 datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/DS18B20.pdf)
specifies a -55°C to +125°C measurement range and a 750 ms maximum conversion
time at its default 12-bit resolution.

The sampling task starts during boot, independently of later Wi-Fi and MQTT
reconnects. Every five seconds by default it asks the physical probe for a new
conversion. It checks the driver result (including scratchpad CRC and the
unconverted power-on value) and accepts only finite values within the sensor's
range. A successful read logs
`sensor_state=valid temperature_c=...`. A missing probe logs
`sensor_state=error reason=disconnected`; CRC, invalid-value, and bus failures
have distinct reasons. Invalid samples never log a numeric temperature and are
never treated as a valid reading. The task tries again next period, so the probe
can be connected later without a firmware reboot. In normal mode, each valid
sample becomes one JSON event at QoS 1, without retain, on
`equipment/{device_id}/telemetry`.
`measured_at` is `null` with `quality.clock=unsynchronised` until SNTP confirms
the clock. After synchronization it contains UTC measurement time and the clock
quality is `synchronised`. Reconnect retries preserve the original event bytes.

The publisher retains one pending event and up to 32 further readings in RAM.
It retries an unacknowledged event after 20 seconds and on reconnect. A full
queue drops the new reading and logs `telemetry_dropped`; reboot loses RAM events.
QoS 1 may deliver duplicates. Broker acknowledgement confirms broker receipt,
not gateway or backend persistence.

The dashboard currently displays stored telemetry, which can come from the
simulator. It marks missing readings as unavailable and explains that live sensor
fault status is not available through the current device API. A stored older
reading does not prove the physical sensor is still connected.

## Host check and hardware validation

From the repository root, the host tests need only a C compiler:

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
gcc -std=gnu11 -Wall -Wextra -Werror \
  -I firmware/tests/stubs -I firmware/components/temperature_sensor/include \
  firmware/components/temperature_sensor/temperature_sensor.c \
  firmware/tests/test_temperature_sensor.c -o /tmp/iemp-firmware-test-temperature
/tmp/iemp-firmware-test-temperature
gcc -std=c11 -Wall -Wextra -Werror -pedantic \
  -I firmware/components/identity/include \
  -I firmware/components/telemetry/include \
  firmware/components/identity/identity.c \
  firmware/components/telemetry/telemetry_encoding.c \
  firmware/tests/test_telemetry_encoding.c -o /tmp/iemp-firmware-test-telemetry
/tmp/iemp-firmware-test-telemetry
```

Physical-sensor validation requires a board, USB serial access, a DS18B20, and
valid Wi-Fi credentials. First observe `reason=disconnected` with DQ unplugged. After
wiring, compare logged values against a trusted thermometer at stable ambient
temperature; then disconnect DQ and confirm the next sample reports an error
without a numeric temperature. Record the board revision, probe, wiring,
ESP-IDF version, firmware commit, serial port, and two boot logs.
Subscribe with the gateway credential at QoS 1 to `equipment/+/telemetry` before
powering the board. Verify one valid event every five seconds, with the same boot
ID and increasing sequence. Reconnect Wi-Fi and check that both continue; reboot
and check for a new boot ID and sequence zero. In normal mode a missing probe
must yield no temperature event; in synthetic demo mode it should keep publishing
the configured constant. See [Firmware Coding Conventions](CODING_CONVENTIONS.md).
