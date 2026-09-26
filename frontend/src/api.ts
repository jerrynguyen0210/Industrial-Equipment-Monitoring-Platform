/** Public, build-time browser configuration. The default uses the local proxy. */
const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();

export const apiBaseUrl = (configuredBaseUrl || "/api").replace(/\/+$/, "");

export type ReadinessResponse = {
  status: "ready";
  database: "ok";
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
