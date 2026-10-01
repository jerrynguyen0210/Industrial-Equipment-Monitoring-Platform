# Build and flash the ESP32

Connect one ESP32-DevKitC-compatible board by USB. From the repository root,
run as your normal user:

```sh
./agents/hardware_script/compile-and-flash-esp32.sh --monitor
```

The script installs or reuses a shallow ESP-IDF 5.5.4 checkout on supported
Linux hosts, opens `menuconfig` when firmware settings need attention, prompts
twice for the device's MQTT password without displaying it, builds the firmware, and flashes
the selected board. In `menuconfig`, set the registered device ID (also the MQTT
username), Wi-Fi settings, the broker's reachable LAN address, and the sensor
source. The MQTT password must match the account provisioned for that device;
for the lab demo it is in the ignored
`secrets/mosquitto/device-demo-001.password` file. Leave the MQTT password field
in `menuconfig` empty because the script will ask for it after you save and exit.

If multiple serial devices are connected, pass `--port /dev/ttyUSB0` (or the
correct device). Use `--configure` to reopen `menuconfig`. Run `--help` for all
options. The old `Setup_Guide/compile-and-flash-esp32.sh` path still works.

Keep `firmware/sdkconfig` and `firmware/build/` private: both contain the MQTT
password, and the firmware image also contains the Wi-Fi passphrase. Flashing
updates the application without intentionally erasing the ESP32's NVS partition.
