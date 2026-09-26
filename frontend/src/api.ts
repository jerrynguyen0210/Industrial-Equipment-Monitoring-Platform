/** Public, build-time browser configuration. The default uses the local proxy. */
const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();

export const apiBaseUrl = (configuredBaseUrl || "/api").replace(/\/+$/, "");

export type ReadinessResponse = {
  status: "ready";
  database: "ok";
};

export type LatestReading = {
  value: number;
  unit: string;
  measured_at: string | null;
  clock_quality: "synchronised" | "unsynchronised" | "estimated" | "unknown";
};

export type DeviceStatus = {
  device_id: string;
  name: string;
  latest_reading: LatestReading | null;
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

function isLatestReading(value: unknown): value is LatestReading {
  if (typeof value !== "object" || value === null) return false;
  if (
    !("value" in value) ||
    typeof value.value !== "number" ||
    !Number.isFinite(value.value) ||
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
