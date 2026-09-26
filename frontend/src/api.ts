/** Public, build-time browser configuration. The default uses the local proxy. */
const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();

export const apiBaseUrl = (configuredBaseUrl || "/api").replace(/\/+$/, "");

export type ReadinessResponse = {
  status: "ready";
  database: "ok";
};

export type LatestReading = {
  value: number | string;
  unit: string;
  measured_at: string | null;
  clock_quality: "synchronised" | "unsynchronised" | "estimated" | "unknown";
};

export type DeviceStatus = {
  device_id: string;
  name: string;
  latest_reading: LatestReading | null;
};

export type HistoryPoint = {
  measured_at: string;
  value: number | string;
  gap_before: boolean;
};

export type DeviceHistory = {
  device_id: string;
  unit: string;
  range_start: string;
  range_end: string;
  truncated: boolean;
  points: HistoryPoint[];
};

function isReadinessResponse(value: unknown): value is ReadinessResponse {
  return (
    typeof value === "object" &&
    value !== null &&
    "status" in value &&
    value.status === "ready" &&
    "database" in value &&
    value.database === "ok"
  );
}

export async function getReadiness(
  signal: AbortSignal,
): Promise<ReadinessResponse> {
  const response = await fetch(`${apiBaseUrl}/health/ready`, {
    signal,
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Readiness request failed with HTTP ${response.status}`);
  }

  const body: unknown = await response.json();
  if (!isReadinessResponse(body)) {
    throw new Error("Invalid readiness response");
  }

  return body;
}

function isTemperatureValue(value: unknown): value is number | string {
  if (typeof value === "number") return Number.isFinite(value);
  return (
    typeof value === "string" &&
    /^-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$/.test(value) &&
    Number.isFinite(Number(value))
  );
}

function isLatestReading(value: unknown): value is LatestReading {
  if (typeof value !== "object" || value === null) return false;
  if (
    !("value" in value) ||
    !isTemperatureValue(value.value) ||
    !("unit" in value) ||
    typeof value.unit !== "string" ||
    !("measured_at" in value) ||
    (value.measured_at !== null && typeof value.measured_at !== "string") ||
    !("clock_quality" in value) ||
    !["synchronised", "unsynchronised", "estimated", "unknown"].includes(
      String(value.clock_quality),
    )
  ) {
    return false;
  }
  return true;
}

function isDeviceStatus(value: unknown): value is DeviceStatus {
  return (
    typeof value === "object" &&
    value !== null &&
    "device_id" in value &&
    typeof value.device_id === "string" &&
    "name" in value &&
    typeof value.name === "string" &&
    "latest_reading" in value &&
    (value.latest_reading === null || isLatestReading(value.latest_reading))
  );
}

export async function getDevices(signal: AbortSignal): Promise<DeviceStatus[]> {
  const response = await fetch(`${apiBaseUrl}/v1/devices`, {
    signal,
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Device request failed with HTTP ${response.status}`);
  }

  const body: unknown = await response.json();
  if (
    typeof body !== "object" ||
    body === null ||
    !("devices" in body) ||
    !Array.isArray(body.devices) ||
    !body.devices.every(isDeviceStatus)
  ) {
    throw new Error("Invalid device response");
  }

  return body.devices;
}

function isTimestamp(value: unknown): value is string {
  return typeof value === "string" && Number.isFinite(Date.parse(value));
}

function isHistoryPoint(value: unknown): value is HistoryPoint {
  return (
    typeof value === "object" &&
    value !== null &&
    "measured_at" in value &&
    isTimestamp(value.measured_at) &&
    "value" in value &&
    isTemperatureValue(value.value) &&
    "gap_before" in value &&
    typeof value.gap_before === "boolean"
  );
}

function isDeviceHistory(value: unknown): value is DeviceHistory {
  return (
    typeof value === "object" &&
    value !== null &&
    "device_id" in value &&
    typeof value.device_id === "string" &&
    "unit" in value &&
    typeof value.unit === "string" &&
    "range_start" in value &&
    isTimestamp(value.range_start) &&
    "range_end" in value &&
    isTimestamp(value.range_end) &&
    "truncated" in value &&
    typeof value.truncated === "boolean" &&
    "points" in value &&
    Array.isArray(value.points) &&
    value.points.every(isHistoryPoint)
  );
}

export async function getDeviceHistory(
  deviceId: string,
  from: Date,
  to: Date,
  signal: AbortSignal,
): Promise<DeviceHistory> {
  const query = new URLSearchParams({
    from: from.toISOString(),
    to: to.toISOString(),
  });
  const response = await fetch(
    `${apiBaseUrl}/v1/devices/${encodeURIComponent(deviceId)}/telemetry/history?${query}`,
    { signal, cache: "no-store" },
  );
  if (!response.ok) {
    throw new Error(`History request failed with HTTP ${response.status}`);
  }

  const body: unknown = await response.json();
  if (!isDeviceHistory(body) || body.device_id !== deviceId) {
    throw new Error("Invalid history response");
  }
  return body;
}
