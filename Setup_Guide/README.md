# Setup and deployment guide

Run repository commands from the repository root unless a step says otherwise.
Commands use Bash on Linux.

Follow these guides in order:

1. [Install and run the lab system](01-lab-installation.md).
2. [Connect the gateway and ESP32](02-hardware-and-gateway.md).
3. [Operate and recover the system](03-operations.md).
4. [Prepare a customer release](04-customer-deployment.md).

For a supported 64-bit Raspberry Pi OS, Debian, or Ubuntu host, the quickest
start is:

```sh
./Setup_Guide/install.sh
```

After connecting the ESP32 by USB:

```sh
./agents/hardware_script/compile-and-flash-esp32.sh --monitor
```

The lab stack includes PostgreSQL, Mosquitto, FastAPI, and a React dashboard.
The native gateway and ESP32 run outside Compose. The dashboard shows stored
readings and server contact status. Its sample alert card is not a live safety
alarm.

Use this system only on a controlled lab network. MQTT and device heartbeats are
unencrypted, dashboard/read APIs have no user login, and production backup,
retention, and fleet operations are incomplete.
