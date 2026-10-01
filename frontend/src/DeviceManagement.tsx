import { useEffect, useState, type FormEvent } from "react";
import {
  configureExistingMqtt,
  getDevices,
  getGateways,
  registerDevice,
  removeDevice,
  type DeviceStatus,
  type Gateway,
} from "./api";

const refreshMs = 15_000;

export function DeviceManagement() {
  const [devices, setDevices] = useState<DeviceStatus[]>([]);
  const [gateways, setGateways] = useState<Gateway[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [removeMessage, setRemoveMessage] = useState("");
  const [removeError, setRemoveError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [mqttSaving, setMqttSaving] = useState(false);
  const [mqttMessage, setMqttMessage] = useState("");
  const [mqttError, setMqttError] = useState("");

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    let controller: AbortController;
    async function refresh() {
      controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 6000);
      try {
        const [nextDevices, nextGateways] = await Promise.all([
          getDevices(controller.signal),
          getGateways(controller.signal),
        ]);
        if (!stopped) {
          setDevices(nextDevices);
          setGateways(nextGateways);
          setLoadError(false);
        }
      } catch {
        if (!stopped) setLoadError(true);
      } finally {
        clearTimeout(timeout);
        if (!stopped) {
          setLoading(false);
          timer = setTimeout(refresh, refreshMs);
        }
      }
    }
    void refresh();
    return () => {
      stopped = true;
      clearTimeout(timer);
      controller?.abort();
    };
  }, [refreshKey]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setSaving(true);
    setError("");
    setMessage("");
    try {
      await registerDevice({
        device_id: String(data.get("device_id") || "").trim(),
        gateway_id: String(data.get("gateway_id") || ""),
        name: String(data.get("name") || "").trim(),
        password: String(data.get("password") || ""),
      });
      form.reset();
      setMessage(
        "Device and MQTT account registered. It will show online after its first heartbeat or accepted reading.",
      );
      setRefreshKey((key) => key + 1);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Registration failed.");
    } finally {
      setSaving(false);
    }
  }

  async function submitExistingMqtt(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const deviceId = String(data.get("existing_device_id") || "");
    setMqttSaving(true);
    setMqttMessage("");
    setMqttError("");
    try {
      await configureExistingMqtt(
        deviceId,
        String(data.get("existing_password") || ""),
      );
      form.reset();
      setMqttMessage(`MQTT account is ready for ${deviceId}.`);
    } catch (cause) {
      setMqttError(
        cause instanceof Error ? cause.message : "MQTT setup failed.",
      );
    } finally {
      setMqttSaving(false);
    }
  }

  async function remove(device: DeviceStatus) {
    if (
      !window.confirm(
        `Remove ${device.name} (${device.device_id}) from the server? This cannot be undone. Devices with saved history cannot be removed.`,
      )
    ) {
      return;
    }
    setRemovingId(device.device_id);
    setRemoveError("");
    setRemoveMessage("");
    try {
      await removeDevice(device.device_id);
      setDevices((current) =>
        current.filter((item) => item.device_id !== device.device_id),
      );
      setRemoveMessage(`${device.name} was removed.`);
      setRefreshKey((key) => key + 1);
    } catch (cause) {
      setRemoveError(
        cause instanceof Error ? cause.message : "Device removal failed.",
      );
    } finally {
      setRemovingId(null);
    }
  }

  return (
    <>
      <div className="page-heading">
        <p className="eyebrow">Equipment monitoring</p>
        <h1 id="page-title" tabIndex={-1}>
          Device management
        </h1>
        <p className="page-description">
          Register devices and check their recent connection to the server.
        </p>
      </div>
      <div className="device-management-grid">
        <section className="panel" aria-labelledby="register-heading">
          <h2 id="register-heading">Register a device</h2>
          <form
            className="device-form"
            onSubmit={(event) => void submit(event)}
          >
            <label htmlFor="device-name">Device name</label>
            <input
              id="device-name"
              name="name"
              maxLength={200}
              required
              placeholder="Boiler room ESP32"
            />
            <label htmlFor="device-id">Device ID</label>
            <input
              id="device-id"
              name="device_id"
              maxLength={128}
              pattern="[A-Za-z0-9_-]+"
              required
              placeholder="esp32-boiler-01"
            />
            <label htmlFor="device-gateway">Gateway</label>
            <select
              id="device-gateway"
              name="gateway_id"
              required
              disabled={gateways.length === 0}
            >
              <option value="">Select a gateway</option>
              {gateways.map((gateway) => (
                <option key={gateway.gateway_id} value={gateway.gateway_id}>
                  {gateway.name} ({gateway.gateway_id})
                </option>
              ))}
            </select>
            <label htmlFor="device-password">Device password</label>
            <input
              id="device-password"
              name="password"
              type="password"
              minLength={12}
              maxLength={128}
              autoComplete="new-password"
              required
            />
            <p className="form-help">
              Registration creates the MQTT account automatically. The MQTT
              username is the Device ID, and this password also authenticates
              backend heartbeats. Set both values in the ESP32 firmware.
            </p>
            <button
              className="primary-link"
              type="submit"
              disabled={saving || gateways.length === 0}
            >
              {saving ? "Registering…" : "Register device"}
            </button>
          </form>
          {message && (
            <p role="status" className="form-success">
              {message}
            </p>
          )}
          {error && (
            <p role="alert" className="equipment-error">
              {error}
            </p>
          )}
          {devices.length > 0 && (
            <form
              className="device-form existing-mqtt-form"
              onSubmit={(event) => void submitExistingMqtt(event)}
            >
              <h3>Set up MQTT for an existing device</h3>
              <p className="form-help">
                For devices registered before automatic MQTT setup, enter their
                original registration password here.
              </p>
              <label htmlFor="existing-mqtt-device">Registered device</label>
              <select
                id="existing-mqtt-device"
                name="existing_device_id"
                required
              >
                <option value="">Select a device</option>
                {devices.map((device) => (
                  <option key={device.device_id} value={device.device_id}>
                    {device.name} ({device.device_id})
                  </option>
                ))}
              </select>
              <label htmlFor="existing-mqtt-password">
                Registration password
              </label>
              <input
                id="existing-mqtt-password"
                name="existing_password"
                type="password"
                minLength={12}
                maxLength={128}
                autoComplete="current-password"
                required
              />
              <button
                className="primary-link"
                type="submit"
                disabled={mqttSaving}
              >
                {mqttSaving ? "Setting up…" : "Set up MQTT account"}
              </button>
              {mqttMessage && (
                <p role="status" className="form-success">
                  {mqttMessage}
                </p>
              )}
              {mqttError && (
                <p role="alert" className="equipment-error">
                  {mqttError}
                </p>
              )}
            </form>
          )}
          {!loading && gateways.length === 0 && (
            <p className="equipment-message">
              No enabled gateways are available. Add a gateway before
              registering devices.
            </p>
          )}
        </section>
        <section className="panel" aria-labelledby="registered-heading">
          <div className="section-heading">
            <h2 id="registered-heading">Registered devices</h2>
            <button
              type="button"
              className="refresh-button"
              onClick={() => setRefreshKey((key) => key + 1)}
            >
              Refresh
            </button>
          </div>
          <p className="form-help">
            Online means the server received a heartbeat or reading in the last
            90 seconds. Offline means no recent backend contact, even if MQTT is
            connected. This list refreshes every 15 seconds. Devices with saved
            readings or alerts cannot be removed.
          </p>
          {loading && <p role="status">Loading devices…</p>}
          {loadError && (
            <p role="alert" className="equipment-error">
              Device list could not be loaded.
            </p>
          )}
          {removeMessage && (
            <p role="status" className="form-success">
              {removeMessage}
            </p>
          )}
          {removeError && (
            <p role="alert" className="equipment-error">
              {removeError}
            </p>
          )}
          {!loading && !loadError && devices.length === 0 && (
            <p>No devices registered yet.</p>
          )}
          {!loadError && (
            <ul className="managed-devices">
              {devices.map((device) => (
                <li key={device.device_id}>
                  <div>
                    <strong>{device.name}</strong>
                    <span>
                      {device.device_id} · {device.gateway_id}
                    </span>
                  </div>
                  <div className="managed-device-presence">
                    <span
                      className={`presence-badge ${device.online ? "online" : "offline"}`}
                    >
                      {device.online ? "Running · online" : "Offline"}
                    </span>
                    <small>
                      {device.last_seen_at
                        ? `Last seen ${new Date(device.last_seen_at).toLocaleString()}`
                        : "Never seen"}
                    </small>
                  </div>
                  <button
                    type="button"
                    className="remove-device-button"
                    aria-label={`Remove ${device.name} (${device.device_id})`}
                    disabled={removingId !== null}
                    onClick={() => void remove(device)}
                  >
                    {removingId === device.device_id ? "Removing…" : "Remove"}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </>
  );
}
