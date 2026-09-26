import { useEffect, useState } from "react";
import { getReadiness } from "./api";

type Status = "checking" | "ready" | "unavailable";

export function PlatformStatus() {
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    let request: AbortController;

    async function refresh() {
      request = new AbortController();
      const timeout = setTimeout(() => request.abort(), 6000);
      try {
        await getReadiness(request.signal);
        if (!stopped) setStatus("ready");
      } catch {
        if (!stopped) setStatus("unavailable");
      } finally {
        clearTimeout(timeout);
        if (!stopped) timer = setTimeout(refresh, 5000);
      }
    }

    void refresh();
    return () => {
      stopped = true;
      clearTimeout(timer);
      request?.abort();
    };
  }, []);

  return (
    <section aria-labelledby="status-heading">
      <h2 id="status-heading">Service status</h2>
      <p role="status" className={`status ${status}`}>
        {status === "checking" && "Checking backend and database…"}
        {status === "ready" && "Backend and database are ready."}
        {status === "unavailable" &&
          "Backend or database is unavailable. Retrying automatically…"}
      </p>
      <p>
        This checks the local platform connection. Equipment monitoring,
        telemetry ingestion, and alerts are not implemented yet.
      </p>
    </section>
  );
}
