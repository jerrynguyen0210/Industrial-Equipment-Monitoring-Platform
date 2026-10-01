import { useEffect, useState } from "react";
import { getDevices, type DeviceStatus as Device } from "./api";

const refreshIntervalMs = 15_000;

function formatMeasurementTime(device: Device): string {
  const reading = device.latest_reading;
  if (!reading) return "Reading time unavailable";

  const eventAt = new Date(reading.event_at);
  if (!Number.isFinite(eventAt.getTime())) return "Reading time unavailable";

  const ageSeconds = Math.floor((Date.now() - eventAt.getTime()) / 1000);
  const age =
    ageSeconds < 0
      ? "timestamp is in the future"
      : ageSeconds < 60
        ? `${ageSeconds} sec ago`
        : ageSeconds < 3600
          ? `${Math.floor(ageSeconds / 60)} min ago`
          : ageSeconds < 86_400
            ? `${Math.floor(ageSeconds / 3600)} hr ago`
            : `${Math.floor(ageSeconds / 86_400)} days ago`;
  const timestamp = new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    timeZoneName: "short",
  }).format(eventAt);

  const source =
    reading.timestamp_source === "measured_at"
      ? "Measured"
      : "Gateway received";
  return `${source} ${timestamp} · ${age}`;
}

function ReadingCard({ device }: { device: Device }) {
  const reading = device.latest_reading;

  return (
    <article
      className="equipment-card"
      aria-labelledby={`device-${device.device_id}`}
    >
      <div className="equipment-card-heading">
        <div>
          <h3 id={`device-${device.device_id}`}>{device.name}</h3>
          <p className="device-id">{device.device_id}</p>
        </div>
        <div className="equipment-indicators">
          <span
            className={`presence-badge ${device.online ? "online" : "offline"}`}
          >
            {device.online ? "Running · online" : "Offline"}
          </span>
          <span
            className={`data-indicator ${reading ? "available" : "missing"}`}
          >
            <span aria-hidden="true" />
            {reading ? "Recorded reading" : "No reading"}
          </span>
        </div>
      </div>

      <div className="reading-value">
        {reading ? (
          <>
            <strong>{reading.value}</strong>
            <span>{reading.unit}</span>
          </>
        ) : (
          <strong className="reading-unavailable">Unavailable</strong>
        )}
      </div>
      <p className="reading-time">
        {reading
          ? formatMeasurementTime(device)
          : "No valid temperature reading has been recorded."}
      </p>
      <p className="sensor-state-note">
        {device.last_seen_at
          ? `Last server contact ${new Date(device.last_seen_at).toLocaleString()}.`
          : "No server contact recorded yet."}
      </p>
      <p className="alert-count">Active alerts: unavailable</p>
    </article>
  );
}

export function EquipmentStatus() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(false);
  const [refreshedAt, setRefreshedAt] = useState<Date | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    let request: AbortController;

    async function refresh() {
      request = new AbortController();
      const timeout = setTimeout(() => request.abort(), 6000);
      setRefreshing(true);
      try {
        const result = await getDevices(request.signal);
        if (!stopped) {
          setDevices(result);
          setError(false);
          setRefreshedAt(new Date());
        }
      } catch {
        if (!stopped) setError(true);
      } finally {
        clearTimeout(timeout);
        if (!stopped) {
          setLoading(false);
          setRefreshing(false);
          timer = setTimeout(() => void refresh(), refreshIntervalMs);
        }
      }
    }

    void refresh();
    return () => {
      stopped = true;
      clearTimeout(timer);
      request?.abort();
    };
  }, [refreshKey]);

  return (
    <section className="equipment-panel" aria-labelledby="equipment-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Live equipment</p>
          <h2 id="equipment-heading">Current status</h2>
        </div>
        <button
          className="refresh-button"
          type="button"
          disabled={refreshing}
          onClick={() => setRefreshKey((key) => key + 1)}
        >
          {refreshing ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      <p className="sensor-setup-notice">
        Temperature sensor installation is pending. Recorded values may come
        from the simulator; a missing reading is unavailable, not 0°C. Sensor
        faults are currently reported in firmware logs.
      </p>

      {loading && (
        <p className="equipment-message" role="status">
          Loading equipment status…
        </p>
      )}
      {error && (
        <p className="equipment-error" role="alert">
          Equipment status could not be loaded. Check the backend connection and
          try refreshing.
        </p>
      )}
      {!loading && devices.length === 0 && !error && (
        <p className="equipment-message">
          No devices are registered yet. Register a device to see its current
          status here.
        </p>
      )}
      {devices.length > 0 && !error && (
        <div className="equipment-list">
          {devices.map((device) => (
            <ReadingCard key={device.device_id} device={device} />
          ))}
        </div>
      )}
      {refreshedAt && (
        <p className="dashboard-refresh-time">
          Dashboard data refreshed at {refreshedAt.toLocaleTimeString()}.
        </p>
      )}
    </section>
  );
}
