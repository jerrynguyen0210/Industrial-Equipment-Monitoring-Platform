# 2. Connect the gateway and ESP32

Complete [the lab installation](01-lab-installation.md) first. This guide uses
the seeded demo IDs and credentials. The project supports one externally powered
DS18B20 temperature probe per ESP32. Test all wiring with power removed and
verify the probe's actual pinout against its supplier's markings; bare devices
and cabled modules may have different lead colours.

## Physical layout

```text
DS18B20 DQ ── ESP32 GPIO 4 (or configured GPIO)
          └── 4.7 kΩ resistor ── ESP32 3.3 V
DS18B20 VDD ── ESP32 3.3 V
DS18B20 GND ── ESP32 GND

ESP32 -- 2.4 GHz Wi-Fi -- Mosquitto host:1883
Linux gateway -- MQTT subscription -- Mosquitto host:1883
Linux gateway -- HTTP batches -- backend host:8000
```

Use a regulated supply suitable for the ESP32 board, a common ground, and a
4.7 kΩ pull-up from DQ to **3.3 V** unless the sensor module has one. Never pull
the ESP32 data pin to 5 V. Parasitic power and multiple probes on one bus are
not supported by this firmware. Default sample interval is five seconds.

The broker and backend in Compose bind to `127.0.0.1` by default. If the ESP32 or
a separate Raspberry Pi must reach the host across a **controlled lab LAN**, set
`MQTT_BIND_ADDRESS` to the host's reachable LAN IPv4 address in root `.env`; also
set `BACKEND_BIND_ADDRESS` if the Pi needs the API. Limit access with the host
firewall and recreate the services:

```sh
docker compose up -d --wait --force-recreate mosquitto backend frontend
```

Use that LAN address in clients. `127.0.0.1` on the ESP32/Pi is the device
itself; Compose service names such as `mosquitto` work only inside Compose.
Leave the dashboard bound to loopback unless a controlled lab viewer needs it.
The local MQTT listener is **unencrypted**; do not expose port 1883 to the
internet or an untrusted site network.

## Install the native gateway

For a new Raspberry Pi, use [Raspberry Pi Imager's headless setup](https://www.raspberrypi.com/documentation/computers/getting-started.html)
to install Raspberry Pi OS Lite, set a unique account and hostname, configure
network access, and enable SSH. Boot it with a suitable power supply; confirm
network reachability and correct time with `timedatectl status`. Give the Pi a
stable DNS name or address that the operator can reach. Keep the SQLite queue
on persistent storage, not a temporary filesystem.

On Raspberry Pi OS, Debian, or Ubuntu, install build dependencies and compile
from the repository root. The Pi should have persistent writable local storage
for its SQLite queue and reliable network/power. A Pi is optional: the gateway
can run on the same Linux host as Compose.

If building on the Compose host, stop the container broker before installing the
native `mosquitto` test package, which may start its own service on port 1883:

```sh
docker compose stop mosquitto
```

```sh
sudo apt-get update
sudo apt-get install cmake g++ libsqlite3-dev libmosquitto-dev libcurl4-openssl-dev nlohmann-json3-dev python3 mosquitto mosquitto-clients
sudo systemctl disable --now mosquitto
cmake -S gateway -B gateway/build -DCMAKE_BUILD_TYPE=Release
cmake --build gateway/build --parallel 2
ctest --test-dir gateway/build --output-on-failure
```

The `systemctl` line applies to systemd-based hosts with the packaged Mosquitto
unit. The test suite starts its own broker process. On the Compose host, restart
the container broker after the native service is stopped:

```sh
docker compose up -d --wait mosquitto
```

On the Compose host, `gateway/.env` was copied in step 1. On a separate Pi,
check out the same repository revision, copy `gateway/.env.example` to
`gateway/.env`, and transfer **only** the gateway MQTT password into
`secrets/mosquitto/gateway-demo-001.password` through a protected channel. Set
mode 0600 on that file and `gateway/.env` before editing either. Transfer the
API token securely as well; it belongs in
the gateway config, not in a shell command or Git. Set `MQTT_HOST` and
`API_BASE_URL` to the broker/backend host address from the gateway's
perspective. `API_BASE_URL` must end in `/api`. Use
`MQTT_USERNAME=gateway-demo-001` and point `MQTT_PASSWORD_FILE` to the generated
gateway password. Do not copy the whole broker auth directory to the Pi. The
backend token in `GATEWAY_API_KEY` must match the root `.env` mapping.
`QUEUE_DB_PATH` needs a persistent writable parent.

```sh
gateway/build/gateway --config gateway/.env --check-config
gateway/build/gateway --config gateway/.env
```

Run the second command in a dedicated terminal for initial testing. Expect
`ready` and then `subscribed` in JSON logs. `ready` alone does not mean the MQTT
subscription succeeded. For a persistent lab gateway service, stop the terminal
process and use the supplied
[`gateway.service.example`](../gateway/gateway.service.example). On a systemd
host, after preparing the local `gateway/.env` and gateway MQTT password as
above, run from the repository root:

```sh
sudo cmake --install gateway/build --prefix /usr/local
sudo useradd --system --home /var/lib/iemp-gateway --shell /usr/sbin/nologin iemp-gateway
sudo install -d -m 0700 -o iemp-gateway -g iemp-gateway /etc/iemp-gateway
sudo install -m 0600 -o iemp-gateway -g iemp-gateway gateway/.env /etc/iemp-gateway/gateway.env
sudo install -m 0600 -o iemp-gateway -g iemp-gateway secrets/mosquitto/gateway-demo-001.password /etc/iemp-gateway/mqtt.password
sudo install -m 0644 gateway/gateway.service.example /etc/systemd/system/iemp-gateway.service
```

Edit `/etc/iemp-gateway/gateway.env` so `MQTT_PASSWORD_FILE` is
`/etc/iemp-gateway/mqtt.password`, both host addresses are reachable, and the
gateway API token matches the backend. The unit overrides `QUEUE_DB_PATH` with
`/var/lib/iemp-gateway/queue.sqlite3`, and systemd creates that directory.
Then validate and enable it:

```sh
sudo -u iemp-gateway /usr/local/bin/gateway --config /etc/iemp-gateway/gateway.env --check-config
sudo systemctl daemon-reload
sudo systemctl enable --now iemp-gateway
systemctl status iemp-gateway
journalctl -u iemp-gateway -f
```

The `useradd` command is for first installation; skip it if the service account
already exists. See the [gateway guide](../gateway/README.md) for queue and
restart semantics.

## Configure and flash the ESP32

### Automated firmware build and flash

Connect one ESP32-DevKitC-compatible board to the Linux host with a data-capable
USB cable, then run from the repository root as your normal user:

```sh
./Setup_Guide/compile-and-flash-esp32.sh --monitor
```

On Raspberry Pi OS, Debian, and Ubuntu, the script installs the build packages,
clones the pinned ESP-IDF 5.5.4 release under the user's local data directory,
installs the ESP32 compiler, builds the firmware, detects the serial port, and
flashes the board. The first run opens `menuconfig` for the required device,
Wi-Fi, MQTT, and sensor settings. Later runs validate and reuse the ignored
`firmware/sdkconfig`, making compilation and upload a single command. The script
never runs a full-chip erase or intentionally erases NVS; normal flashing only
updates the firmware-related partitions.

If more than one serial device is connected, select the board explicitly:

```sh
./Setup_Guide/compile-and-flash-esp32.sh --port /dev/ttyUSB0 --monitor
```

Use `--configure` to reopen configuration, or `--skip-host-install` on another
64-bit Linux distribution after installing ESP-IDF's prerequisites. If the
script reports a serial permission error, add the user to the reported group
(usually `dialout`), log out and back in, and rerun. Run
`./Setup_Guide/compile-and-flash-esp32.sh --help` for all options. Keep
`firmware/sdkconfig` and the generated firmware image private because they
contain Wi-Fi and MQTT credentials.

### Manual firmware build and flash

Use an ESP32-DevKitC-compatible board with an ESP32 and USB serial. Install and
activate ESP-IDF **5.5.4** for ESP32. On Debian/Ubuntu, follow the pinned
[Espressif installation steps](https://docs.espressif.com/projects/esp-idf/en/v5.5.4/esp32/get-started/linux-macos-setup.html):

```sh
sudo apt-get install git wget flex bison gperf python3 python3-pip python3-venv cmake ninja-build ccache libffi-dev libssl-dev dfu-util libusb-1.0-0
mkdir -p ~/esp
git clone -b v5.5.4 --recursive https://github.com/espressif/esp-idf.git ~/esp/esp-idf
cd ~/esp/esp-idf
./install.sh esp32
. ./export.sh
cd -
```

Activate with `. ~/esp/esp-idf/export.sh` in each new terminal. Then, from
this repository's `firmware/` directory (see also the
[firmware guide](../firmware/README.md)):

```sh
cd firmware
idf.py menuconfig
idf.py build
idf.py -p /dev/ttyUSB0 flash monitor
```

Replace `/dev/ttyUSB0` with the actual serial port; serial-device permission may
require a host group change. In **Industrial Equipment Monitoring firmware** set:

| Setting | Lab value or rule |
| --- | --- |
| Registered device ID | `device-demo-001`, exactly matching the seed and MQTT account. |
| Wi-Fi SSID/password | The 2.4 GHz WPA2/WPA3 network used by the device; passphrase 8–63 bytes. |
| MQTT host/port | Reachable broker LAN address, port `1883` unless overridden. |
| MQTT password | Contents of `secrets/mosquitto/device-demo-001.password`; username is the device ID. |
| Sensor GPIO | GPIO 4 for the wiring above, or the actual selected pin. |
| Temperature source | DS18B20 for physical monitoring; select web entry for an unwired lab demo. |
| Web temperature entry key | Required only for web entry; a separate device-specific 8–63 character key without spaces. |
| Synthetic source | Select only for a fixed-value lab demo. |

The local `firmware/sdkconfig` and generated image contain credentials; protect
them and do not commit or distribute them. Preserve the ESP32 NVS partition when
reflashing: its committed boot counter is part of event identity. The firmware
publishes valid readings with MQTT QoS 1 and retain disabled. Until SNTP confirms
time, `measured_at` is null and clock quality is `unsynchronised`.

## Verify the full path

1. With the probe disconnected, confirm serial logs report
   `sensor_state=error reason=disconnected` and no numeric reading. Power down,
   wire the probe, then restart.
2. Confirm serial logs show `identity_ready`, Wi-Fi `state=connected`, and
   `sensor_state=valid temperature_c=...`. Compare the stable reading with a
   trusted thermometer. A missing probe must not create a valid event.
3. Check gateway logs for `subscribed`, `message_stored`, and `batch_applied`.
   The last event means the backend confirmed an outcome; MQTT PUBACK alone does
   not establish database storage.
4. Check the dashboard Overview and History pages, or query the database:

```sh
docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT device_id, boot_id, sequence_number, value, backend_received_at FROM telemetry ORDER BY id DESC LIMIT 5"'
```

Expect the physical device ID, increasing sequence within one boot, and a new
boot ID with sequence zero after a reset. Power down, disconnect DQ, restart,
and confirm no new valid readings. Stored older readings remain visible; the dashboard does
not report live probe connection state. If `gateway` logs authentication errors,
check the broker account/ACL separately from the backend bearer token.

For a board with no probe, firmware has an explicit synthetic demo mode. It
publishes a constant value that downstream consumers cannot distinguish from a
physical measurement. Use a **separate demo identity**, keep the result out of
customer acceptance evidence, and see the [firmware guide](../firmware/README.md)
for its menuconfig setting.
Alternatively, select web temperature entry and open `http://<ESP32-IP>/` after
the serial log reports `state=connected ip=...`. Submit a Celsius value and the
configured input key. A successful page response means the device queued the
event; verify gateway and backend delivery as above. Use this plain-HTTP input
only on a trusted lab network and a dedicated demo device identity.
