import { useEffect, useState } from "react";
import {
  getDeviceHistory,
  getDevices,
  type DeviceHistory,
  type DeviceStatus,
  type HistoryPoint,
} from "./api";

type TimeZoneChoice = "UTC" | "local";
type RangeChoice = "15m" | "1h" | "6h" | "24h";

const ranges: Record<RangeChoice, number> = {
  "15m": 15 * 60_000,
  "1h": 60 * 60_000,
  "6h": 6 * 60 * 60_000,
  "24h": 24 * 60 * 60_000,
};

function formatTime(instant: string, choice: TimeZoneChoice): string {
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    timeZone: choice === "UTC" ? "UTC" : undefined,
    timeZoneName: "short",
  }).format(new Date(instant));
}

function lineSegments(points: HistoryPoint[]): HistoryPoint[][] {
  const segments: HistoryPoint[][] = [];
  for (const point of points) {
    if (point.gap_before || segments.length === 0) segments.push([]);
    segments[segments.length - 1].push(point);
  }
  return segments;
}

function HistoryChart({
  history,
  timezone,
}: {
  history: DeviceHistory;
  timezone: TimeZoneChoice;
}) {
  const values = history.points.map((point) => Number(point.value));
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const padding = Math.max((maximum - minimum) * 0.1, 0.5);
  const yMin = minimum - padding;
  const yMax = maximum + padding;
  const from = Date.parse(history.range_start);
  const to = Date.parse(history.range_end);
  const x = (point: HistoryPoint) =>
    60 + ((Date.parse(point.measured_at) - from) / (to - from)) * 620;
  const y = (point: HistoryPoint) =>
    250 - ((Number(point.value) - yMin) / (yMax - yMin)) * 220;
  const segments = lineSegments(history.points);

  return (
    <div className="history-chart-wrap">
      <svg
        className="history-chart"
        viewBox="0 0 720 300"
        role="img"
        aria-labelledby="history-chart-title history-chart-description"
      >
        <title id="history-chart-title">Temperature history</title>
        <desc id="history-chart-description">
          Temperature in {history.unit} over the selected time range. Lines stop
          at missing intervals; the table below lists each reading and gap.
        </desc>
        <line className="chart-axis" x1="60" y1="30" x2="60" y2="250" />
        <line className="chart-axis" x1="60" y1="250" x2="680" y2="250" />
        <text className="chart-label" x="52" y="35" textAnchor="end">
          {yMax.toFixed(1)}
        </text>
        <text className="chart-label" x="52" y="250" textAnchor="end">
          {yMin.toFixed(1)}
        </text>
        {segments.map((segment, index) =>
          segment.length > 1 ? (
            <polyline
              key={index}
              className="chart-line"
              points={segment
                .map((point) => `${x(point)},${y(point)}`)
                .join(" ")}
            />
          ) : null,
        )}
        {history.points.map((point, index) => (
          <circle
            key={`${point.measured_at}-${index}`}
            className="chart-point"
            cx={x(point)}
            cy={y(point)}
            r="3.5"
          />
        ))}
      </svg>
      <div className="history-axis-labels" aria-hidden="true">
        <span>{formatTime(history.range_start, timezone)}</span>
        <span>{formatTime(history.range_end, timezone)}</span>
      </div>
    </div>
  );
}

export function History() {
  const [devices, setDevices] = useState<DeviceStatus[]>([]);
  const [deviceLoading, setDeviceLoading] = useState(true);
  const [deviceError, setDeviceError] = useState(false);
  const [selectedDeviceId, setSelectedDeviceId] = useState("");
  const [range, setRange] = useState<RangeChoice>("1h");
  const [timezone, setTimezone] = useState<TimeZoneChoice>("UTC");
  const [refreshKey, setRefreshKey] = useState(0);
  const [history, setHistory] = useState<DeviceHistory | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState(false);

  useEffect(() => {
    let stopped = false;
    const request = new AbortController();
    const timeout = setTimeout(() => request.abort(), 6000);
    void getDevices(request.signal)
      .then((result) => {
        if (stopped) return;
        setDevices(result);
        setSelectedDeviceId(result[0]?.device_id ?? "");
      })
      .catch(() => {
        if (!stopped) setDeviceError(true);
      })
      .finally(() => {
        clearTimeout(timeout);
        if (!stopped) setDeviceLoading(false);
      });
    return () => {
      stopped = true;
      clearTimeout(timeout);
      request.abort();
    };
  }, []);

  useEffect(() => {
    if (!selectedDeviceId) return;
    let stopped = false;
    const request = new AbortController();
    const timeout = setTimeout(() => request.abort(), 6000);
    const to = new Date();
    const from = new Date(to.getTime() - ranges[range]);
    setHistory(null);
    setHistoryError(false);
    setHistoryLoading(true);
    void getDeviceHistory(selectedDeviceId, from, to, request.signal)
      .then((result) => {
        if (!stopped) setHistory(result);
      })
      .catch(() => {
        if (!stopped) setHistoryError(true);
      })
      .finally(() => {
        clearTimeout(timeout);
        if (!stopped) setHistoryLoading(false);
      });
    return () => {
      stopped = true;
      clearTimeout(timeout);
      request.abort();
    };
  }, [selectedDeviceId, range, refreshKey]);

  const localZone = Intl.DateTimeFormat().resolvedOptions().timeZone;

  return (
    <section className="panel history-panel" aria-labelledby="history-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Telemetry</p>
          <h2 id="history-heading">Temperature history</h2>
        </div>
      </div>

      {deviceLoading && <p role="status">Loading devices…</p>}
      {deviceError && (
        <p role="alert">
          Devices could not be loaded. Refresh the page to retry.
        </p>
      )}
      {!deviceLoading && !deviceError && devices.length === 0 && (
        <p>No devices are registered yet.</p>
      )}
      {devices.length > 0 && (
        <>
          <div className="history-controls">
            <label>
              Device
              <select
                value={selectedDeviceId}
                onChange={(event) => setSelectedDeviceId(event.target.value)}
              >
                {devices.map((device) => (
                  <option value={device.device_id} key={device.device_id}>
                    {device.name} ({device.device_id})
                  </option>
                ))}
              </select>
            </label>
            <label>
              Time range
              <select
                value={range}
                onChange={(event) =>
                  setRange(event.target.value as RangeChoice)
                }
              >
                <option value="15m">Last 15 minutes</option>
                <option value="1h">Last hour</option>
                <option value="6h">Last 6 hours</option>
                <option value="24h">Last 24 hours</option>
              </select>
            </label>
            <label>
              Time display
              <select
                value={timezone}
                onChange={(event) =>
                  setTimezone(event.target.value as TimeZoneChoice)
                }
              >
                <option value="UTC">UTC</option>
                <option value="local">Local ({localZone})</option>
              </select>
            </label>
            <button
              className="refresh-button"
              type="button"
              disabled={historyLoading}
              onClick={() => setRefreshKey((key) => key + 1)}
            >
              Refresh
            </button>
          </div>
          <p className="history-timezone">
            Times shown in{" "}
            {timezone === "UTC" ? "UTC" : `local time (${localZone})`}.
          </p>
          {historyLoading && <p role="status">Loading history…</p>}
          {historyError && (
            <p role="alert">History could not be loaded. Try refreshing.</p>
          )}
          {history && history.points.length === 0 && (
            <p>No synchronized readings in this time range.</p>
          )}
          {history && history.points.length > 0 && (
            <>
              {history.truncated && (
                <p className="history-notice">
                  Showing the latest 2,000 readings. Choose a shorter range to
                  see earlier readings.
                </p>
              )}
              <p className="history-unit">Temperature ({history.unit})</p>
              <HistoryChart history={history} timezone={timezone} />
              <details className="history-table">
                <summary>View reading table ({history.points.length})</summary>
                <div className="history-table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th scope="col">Measured at</th>
                        <th scope="col">Temperature ({history.unit})</th>
                        <th scope="col">Line</th>
                      </tr>
                    </thead>
                    <tbody>
                      {history.points.map((point, index) => (
                        <tr key={`${point.measured_at}-${index}`}>
                          <td>{formatTime(point.measured_at, timezone)}</td>
                          <td>{point.value}</td>
                          <td>
                            {index === 0
                              ? "Start"
                              : point.gap_before
                                ? "Gap before"
                                : "Connected"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            </>
          )}
        </>
      )}
    </section>
  );
}
