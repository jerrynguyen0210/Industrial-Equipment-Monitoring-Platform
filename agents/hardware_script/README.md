# Build and flash the ESP32

1. Connect one ESP32-DevKitC-compatible board with a data-capable USB cable.
2. From the repository root, run:

   ```sh
   ./agents/hardware_script/compile-and-flash-esp32.sh --monitor
   ```

3. On the first run, set these values in `menuconfig`:

   - Device ID, exactly matching the dashboard registration.
   - Wi-Fi SSID and password.
   - Server LAN address for MQTT and optional heartbeats.
   - Device password, exactly matching the registration password.
   - Temperature source and GPIO.

4. Save and exit. The script installs or reuses ESP-IDF 5.5.4, builds, flashes,
   and opens the serial monitor.

If several serial devices exist, add `--port /dev/ttyUSB0`. Use `--configure` to
open `menuconfig` again and `--help` for all options.

The Device ID is also the MQTT username. Dashboard registration automatically
creates the matching broker account, so `add_device.py` is not required.

Keep `firmware/sdkconfig`, `firmware/build/`, and firmware images private because
they contain Wi-Fi and MQTT credentials. Normal flashing preserves the ESP32 NVS
boot counter.
