# Run the stack on this machine

1. Open a terminal in the repository root.

2. Start and verify the complete local stack:

   ```sh
   ./agents/server_scripts/run-stack.sh
   ```

   Enter the server and ESP32 addresses when prompted. For an unattended start:

   ```sh
   ./agents/server_scripts/run-stack.sh \
     --server-address 192.168.0.50 \
     --esp32-address 192.168.0.114
   ```

3. Configure the ESP32 firmware MQTT host as `192.168.0.50`, then open the
   dashboard address printed by the script.

4. Reserve `192.168.0.114` for the ESP32 in the router or configure it on the
   device network. The launcher validates and reports this address but cannot
   assign the ESP32's Wi-Fi address.

5. Check status or recent logs:

   ```sh
   ./agents/server_scripts/run-stack.sh status
   ./agents/server_scripts/run-stack.sh logs
   ```

6. Stop services without deleting data:

   ```sh
   ./agents/server_scripts/run-stack.sh stop
   ```

7. On a slower machine, increase the startup timeout:

   ```sh
   ./agents/server_scripts/run-stack.sh start --wait-timeout 300
   ```
