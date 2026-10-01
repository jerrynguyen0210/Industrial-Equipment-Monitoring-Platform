# 2. Connect the gateway and ESP32

Complete [step 1](01-lab-installation.md) first. This procedure uses one
externally powered DS18B20 probe per ESP32.

## 1. Wire the sensor

Disconnect power before changing wiring.

```text
DS18B20 VDD -> ESP32 3.3 V
DS18B20 GND -> ESP32 GND
DS18B20 DQ  -> ESP32 GPIO 4
                 |
                 +-- 4.7 kΩ resistor -> ESP32 3.3 V
```

Check the probe supplier's pinout because wire colours vary. Never pull an ESP32
GPIO to 5 V. Parasitic power and multiple probes are unsupported.

## 2. Expose the lab services on the LAN

1. Restart the stack with the server's reachable LAN address:

   ```sh
   ./agents/server_scripts/run-stack.sh \
     --server-address 192.168.0.50 \
     --esp32-address 192.168.0.114
   ```

2. Replace the example addresses with reserved addresses on your network.
3. Keep MQTT port 1883 inside a trusted lab LAN. The connection is unencrypted.

`127.0.0.1` always means the current machine. Compose names such as `mosquitto`
work only between containers, so an ESP32 or separate Pi must use the server's
LAN address.

## 3. Build and start the native gateway

If `run-stack.sh status` already reports **Gateway running**, skip this section;
the launcher built and started it. Starting a second process against the same
SQLite queue is unsafe.

1. When building manually on the Compose host, stop the container broker before
   installing native Mosquitto. The package may start its own port 1883 service:

   ```sh
   docker compose stop mosquitto
   ```

2. On Raspberry Pi OS, Debian, or Ubuntu, install the build tools:

   ```sh
   sudo apt-get update
   sudo apt-get install cmake g++ libsqlite3-dev libmosquitto-dev \
     libcurl4-openssl-dev nlohmann-json3-dev python3 mosquitto mosquitto-clients
   sudo systemctl disable --now mosquitto
   ```

   Ignore the `systemctl` command on a host without systemd. Restart the Compose
   broker with `docker compose up -d --wait mosquitto`.

3. Build and test from the repository root:

   ```sh
   cmake -S gateway -B gateway/build -DCMAKE_BUILD_TYPE=Release
   cmake --build gateway/build --parallel 2
   ctest --test-dir gateway/build --output-on-failure
   ```

4. Confirm `gateway/.env` contains reachable `MQTT_HOST` and `API_BASE_URL`
   values. `API_BASE_URL` must end in `/api`. Keep the generated gateway MQTT
   password and API token unchanged.
5. Validate and start the process:

   ```sh
   gateway/build/gateway --config gateway/.env --check-config
   gateway/build/gateway --config gateway/.env
   ```

6. Wait for JSON log events `ready` and `subscribed`. `ready` confirms process
   startup; `subscribed` confirms MQTT intake.

For a separate gateway Pi, securely transfer only its gateway password, API
token, and config. Put its SQLite queue on persistent storage. Follow the
[gateway systemd procedure](../gateway/README.md#install-as-a-service) after the
interactive test works.

## 4. Register the ESP32

1. Open the dashboard and select **Device Management**.
2. Select the gateway.
3. Enter a stable Device ID such as `esp-nano`, a clear name, and a unique
   12–128 character password.
4. Select **Register device**.

Registration stores a password hash in PostgreSQL and automatically creates the
Mosquitto account and topic ACL. The Device ID becomes the MQTT username, and the
same password authenticates MQTT and device heartbeats. You do not need to run
`add_device.py`.

If an older broker account already exists, registration succeeds only when the
password matches it. A duplicate ID or conflicting password returns an error
without creating a partial database registration.

## 5. Configure and flash the ESP32

1. Connect the board by USB with a data-capable cable.
2. Run:

   ```sh
   ./agents/hardware_script/compile-and-flash-esp32.sh --monitor
   ```

3. On the first run, set:

   | Setting | Value |
   | --- | --- |
   | Device ID | The exact registered ID, including case. |
   | Wi-Fi | The device's 2.4 GHz SSID and password. |
   | MQTT host/port | Server LAN address and port `1883`. |
   | MQTT password | The password entered during registration. |
   | Backend heartbeat host/port | Server LAN address and port `8000`. |
   | Temperature source | DS18B20 for the wired probe; web or synthetic only for demos. |
   | Sensor GPIO | GPIO 4 for the wiring above. |

4. Save and exit `menuconfig`. The helper builds, flashes, and opens the serial
   monitor. Use `--port /dev/ttyUSB0` when several ports exist and `--configure`
   to edit saved settings.

Keep `firmware/sdkconfig` and firmware images private because credentials are
embedded. Normal flashing preserves NVS and the boot counter.

## 6. Verify the complete path

1. Confirm the serial log shows `identity_ready`, Wi-Fi `state=connected`, and
   MQTT connection. With heartbeats enabled, the dashboard should show the device
   online after its next accepted heartbeat.
2. Confirm a wired probe logs `sensor_state=valid temperature_c=...`. A missing
   probe must log `reason=disconnected` and publish no numeric reading.
3. Confirm gateway logs show `message_stored` and `batch_applied`.
4. Check Overview and History in the dashboard.
5. Query recent rows when deeper diagnosis is needed:

   ```sh
   docker compose exec -T postgres sh -c \
     'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT device_id, boot_id, sequence_number, value, backend_received_at FROM telemetry ORDER BY id DESC LIMIT 5"'
   ```

An MQTT PUBACK confirms broker receipt only. `message_stored` confirms the
gateway's SQLite commit, and `batch_applied` confirms a backend outcome. The
dashboard marks a device offline after 90 seconds without an accepted heartbeat
or recent reading; it does not prove whether Wi-Fi, MQTT, the sensor, or power
failed.
