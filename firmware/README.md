# ESP32 firmware

ESP-IDF 5.5.4 firmware for an ESP32-DevKitC-compatible board. It can read one
DS18B20 probe, accept a lab temperature from a web page, or publish a fixed
synthetic value. The physical sensor is disabled by default.

## Configure, build, and flash

1. Register the device in the dashboard. Record its exact Device ID and password.
2. Connect the ESP32 by USB.
3. From the repository root, run:

   ```sh
   ./agents/hardware_script/compile-and-flash-esp32.sh --monitor
   ```

4. In `menuconfig`, set the Device ID, 2.4 GHz Wi-Fi, server MQTT address,
   registration password, optional backend heartbeat address, and temperature
   source.
5. Save, flash, and watch for `identity_ready`, `state=connected`, and the selected
   sensor/input state.

The Device ID is the MQTT username. Dashboard registration automatically creates
the broker account. The heartbeat uses the same Device ID/password and runs every
30 seconds when configured. MQTT and heartbeat HTTP are plaintext, so use them
only on a trusted lab LAN.

`sdkconfig` and firmware images contain credentials and are ignored by Git. Keep
them private. Normal flashing preserves NVS; erasing NVS resets the boot counter
and breaks identity continuity.

For manual ESP-IDF operation from `firmware/`:

```sh
idf.py menuconfig
idf.py build
idf.py -p /dev/ttyUSB0 flash monitor
```

## Connect a DS18B20

1. Remove power.
2. Connect VDD to 3.3 V, GND to ground, and DQ to the configured GPIO (default 4).
3. Add a 4.7 kΩ pull-up from DQ to 3.3 V unless the module includes one.
4. Power on and select the DS18B20 source.

Do not pull DQ to 5 V. Parasitic power and multiple probes are unsupported.
Valid range is -55°C to 125°C. Missing, CRC-failed, power-on, nonfinite, and
out-of-range samples are logged and never published as valid readings.

## Lab input modes

### Browser entry

1. Select **Enter temperatures on the ESP32 web page**.
2. Configure a separate 8–63 character input key.
3. After Wi-Fi connects, open `http://<esp32-ip>/` on the same trusted network.
4. Enter a Celsius value and the key.

The page reports when an event enters the RAM queue; backend delivery may happen
later. Manual readings have no source marker in telemetry, so use a dedicated
demo Device ID.

### Synthetic value

Select **Demo-only synthetic temperature** and configure hundredths of a degree
(for example, `2500` is 25.00°C). It publishes at the sampling interval. Use a
dedicated demo identity because downstream systems see a valid temperature.

## Identity and delivery

Boot ID is `<factory-MAC>-<NVS-boot-counter>` and changes at each normal reboot.
Sequence starts at zero per boot and never wraps. Wi-Fi reconnects change neither.

Valid readings publish as non-retained MQTT QoS 1 events. Before SNTP sync,
`measured_at` is null and clock quality is `unsynchronised`. Firmware retains one
pending event plus 32 queued events in RAM; reboot loses them. A full queue drops
new readings and may create sequence gaps. Broker acknowledgement does not prove
gateway or backend storage.

## Verify hardware

1. With DQ disconnected, confirm `reason=disconnected` and no numeric reading.
2. Connect the probe and compare stable output with a trusted thermometer.
3. Confirm MQTT events share one boot ID and increase sequence numbers.
4. Reconnect Wi-Fi and confirm identity continues.
5. Reboot and confirm a new boot ID with sequence zero.
6. Disconnect DQ again and confirm publication stops.

Host test commands are encoded in CI. See [Firmware Coding Conventions](CODING_CONVENTIONS.md)
and the [MQTT contract](../docs/mqtt-topic-contract.md).
