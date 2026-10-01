# Run the local stack

1. Open a terminal at the repository root.
2. Start the stack:

   ```sh
   ./agents/server_scripts/run-stack.sh
   ```

3. Enter the server and ESP32 LAN addresses. For unattended startup:

   ```sh
   ./agents/server_scripts/run-stack.sh \
     --server-address 192.168.0.50 \
     --esp32-address 192.168.0.114
   ```

4. Configure the ESP32 MQTT and heartbeat host as the server address, then open
   the dashboard URL printed by the script.
5. Reserve the ESP32 address in the router. The launcher validates this address
   but cannot assign it.
6. Operate the stack:

   ```sh
   ./agents/server_scripts/run-stack.sh status
   ./agents/server_scripts/run-stack.sh logs
   ./agents/server_scripts/run-stack.sh stop
   ```

Use `start --wait-timeout 300` on a slower host. Run `--help` for all options.
