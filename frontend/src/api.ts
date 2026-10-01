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
  gateway_received_at: string;
  event_at: string;
  timestamp_source: "measured_at" | "gateway_received_at";
  clock_quality: "synchronised" | "unsynchronised" | "estimated" | "unknown";
};

export type DeviceStatus = {
  device_id: string;
  name: string;
  gateway_id: string;
  enabled: boolean;
  online: boolean;
  last_seen_at: string | null;
  latest_reading: LatestReading | null;
};

export type Gateway = { gateway_id: string; name: string };

export type DeviceRegistration = {
  device_id: string;
  gateway_id: string;
  name: string;
  password: string;
};

export type HistoryPoint = {
  event_at: string;
  timestamp_source: "measured_at" | "gateway_received_at";
  measured_at: string | null;
  gateway_received_at: string;
  clock_quality: LatestReading["clock_quality"];
  value: number | string;
  unit: string;
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

export type AlertRule = {
  high_threshold: number | string;
  recovery_threshold: number | string;
  consecutive_readings: number;
  unit: string;
};

export type AlertEpisode = {
  id: number;
  device_id: string;
  device_name: string;
  state: "active" | "resolved";
  opened_at: string;
  opening_value: number | string;
  resolved_at: string | null;
  resolving_value: number | string | null;
};

export type AlertEpisodeList = {
  rule: AlertRule;
  active_count: number;
  episodes: AlertEpisode[];
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
    !("gateway_received_at" in value) ||
    !isTimestamp(value.gateway_received_at) ||
    !("event_at" in value) ||
    !isTimestamp(value.event_at) ||
    !("timestamp_source" in value) ||
    !["measured_at", "gateway_received_at"].includes(
      String(value.timestamp_source),
    ) ||
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
    "gateway_id" in value &&
    typeof value.gateway_id === "string" &&
    "enabled" in value &&
    typeof value.enabled === "boolean" &&
    "online" in value &&
    typeof value.online === "boolean" &&
    "last_seen_at" in value &&
    (value.last_seen_at === null || isTimestamp(value.last_seen_at)) &&
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

export async function getGateways(signal: AbortSignal): Promise<Gateway[]> {
  const response = await fetch(`${apiBaseUrl}/v1/gateways`, {
    signal,
    cache: "no-store",
  });
  if (!response.ok)
    throw new Error(`Gateway request failed with HTTP ${response.status}`);
  const body: unknown = await response.json();
  if (
    typeof body !== "object" ||
    body === null ||
    !("gateways" in body) ||
    !Array.isArray(body.gateways) ||
    !body.gateways.every(
      (item: unknown) =>
        typeof item === "object" &&
        item !== null &&
        "gateway_id" in item &&
        typeof item.gateway_id === "string" &&
        "name" in item &&
        typeof item.name === "string",
    )
  )
    throw new Error("Invalid gateway response");
  return body.gateways;
}

export async function registerDevice(
  registration: DeviceRegistration,
): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/v1/devices`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(registration),
  });
  if (response.status === 409) {
    const reason = await responseReason(response);
    throw new Error(
      reason === "mqtt_account_exists"
        ? "An MQTT account already uses that Device ID. Use its matching password or choose another ID."
        : "That device ID is already registered.",
    );
  }
  if (response.status === 404)
    throw new Error("The selected gateway is unavailable.");
  if (response.status === 503)
    throw new Error(
      "MQTT broker or device registry is unavailable. Try again.",
    );
  if (!response.ok)
    throw new Error("Registration failed. Check the details and try again.");
}

async function responseReason(response: Response): Promise<string | null> {
  try {
    const body: unknown = await response.json();
    if (
      typeof body === "object" &&
      body !== null &&
      "detail" in body &&
      typeof body.detail === "object" &&
      body.detail !== null &&
      "reason" in body.detail &&
      typeof body.detail.reason === "string"
    )
      return body.detail.reason;
  } catch {
    // The HTTP status still gives a useful fallback message.
  }
  return null;
}

export async function configureExistingMqtt(
  deviceId: string,
  password: string,
): Promise<void> {
  const response = await fetch(
    `${apiBaseUrl}/v1/devices/${encodeURIComponent(deviceId)}/mqtt`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    },
  );
  if (response.status === 401)
    throw new Error(
      "Password does not match this registration. If the device has no saved history, remove and register it again with the desired password.",
    );
  if (response.status === 409)
    throw new Error(
      "An MQTT account already uses this Device ID with a different password or policy.",
    );
  if (response.status === 503)
    throw new Error(
      "MQTT broker or device registry is unavailable. Try again.",
    );
  if (!response.ok) throw new Error("MQTT setup failed. Try again.");
}

export async function removeDevice(deviceId: string): Promise<void> {
  const response = await fetch(
    `${apiBaseUrl}/v1/devices/${encodeURIComponent(deviceId)}`,
    { method: "DELETE" },
  );
  if (response.status === 404)
    throw new Error("This device is no longer registered.");
  if (response.status === 409) {
    const reason = await responseReason(response);
    throw new Error(
      reason === "mqtt_account_conflict"
        ? "This device's MQTT account needs administrator attention before removal."
        : "This device has saved readings or alerts, so removal is blocked.",
    );
  }
  if (response.status === 503)
    throw new Error(
      "MQTT broker or device registry is unavailable. Try again.",
    );
  if (!response.ok) throw new Error("Device removal failed. Try again.");
}

function isTimestamp(value: unknown): value is string {
  return typeof value === "string" && Number.isFinite(Date.parse(value));
}

function isHistoryPoint(value: unknown): value is HistoryPoint {
  return (
    typeof value === "object" &&
    value !== null &&
    "event_at" in value &&
    isTimestamp(value.event_at) &&
    "timestamp_source" in value &&
    ["measured_at", "gateway_received_at"].includes(
      String(value.timestamp_source),
    ) &&
    "measured_at" in value &&
    (value.measured_at === null || isTimestamp(value.measured_at)) &&
    "gateway_received_at" in value &&
    isTimestamp(value.gateway_received_at) &&
    "clock_quality" in value &&
    ["synchronised", "unsynchronised", "estimated", "unknown"].includes(
      String(value.clock_quality),
    ) &&
    "value" in value &&
    isTemperatureValue(value.value) &&
    "unit" in value &&
    typeof value.unit === "string" &&
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

function isAlertRule(value: unknown): value is AlertRule {
  return (
    typeof value === "object" &&
    value !== null &&
    "high_threshold" in value &&
    isTemperatureValue(value.high_threshold) &&
    "recovery_threshold" in value &&
    isTemperatureValue(value.recovery_threshold) &&
    "consecutive_readings" in value &&
    typeof value.consecutive_readings === "number" &&
    "unit" in value &&
    typeof value.unit === "string"
  );
}

function isAlertEpisode(value: unknown): value is AlertEpisode {
  return (
    typeof value === "object" &&
    value !== null &&
    "id" in value &&
    typeof value.id === "number" &&
    "device_id" in value &&
    typeof value.device_id === "string" &&
    "device_name" in value &&
    typeof value.device_name === "string" &&
    "state" in value &&
    ["active", "resolved"].includes(String(value.state)) &&
    "opened_at" in value &&
    isTimestamp(value.opened_at) &&
    "opening_value" in value &&
    isTemperatureValue(value.opening_value) &&
    "resolved_at" in value &&
    (value.resolved_at === null || isTimestamp(value.resolved_at)) &&
    "resolving_value" in value &&
    (value.resolving_value === null ||
      isTemperatureValue(value.resolving_value))
  );
}

export async function getAlerts(
  signal: AbortSignal,
): Promise<AlertEpisodeList> {
  const response = await fetch(`${apiBaseUrl}/v1/alerts`, {
    signal,
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Alert request failed with HTTP ${response.status}`);
  }

  const body: unknown = await response.json();
  if (
    typeof body !== "object" ||
    body === null ||
    !("rule" in body) ||
    !isAlertRule(body.rule) ||
    !("active_count" in body) ||
    typeof body.active_count !== "number" ||
    !("episodes" in body) ||
    !Array.isArray(body.episodes) ||
    !body.episodes.every(isAlertEpisode)
  ) {
    throw new Error("Invalid alert response");
  }

  return body as AlertEpisodeList;
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
    `${apiBaseUrl}/v1/devices/${encodeURIComponent(deviceId)}/telemetry?${query}`,
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
