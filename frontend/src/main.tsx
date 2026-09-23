import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type Status = "checking" | "ready" | "unavailable";

function PlatformStatus() {
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    let request: AbortController;

    async function refresh() {
      request = new AbortController();
      const timeout = setTimeout(() => request.abort(), 6000);
      try {
        const response = await fetch("/api/health/ready", {
          signal: request.signal,
          cache: "no-store",
        });
        const body: unknown = await response.json();
        const ready =
          response.ok &&
          typeof body === "object" &&
          body !== null &&
          "status" in body &&
          body.status === "ready" &&
          "database" in body &&
          body.database === "ok";
        if (!stopped) setStatus(ready ? "ready" : "unavailable");
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
    <main>
      <p className="eyebrow">Local development</p>
      <h1>Industrial Equipment Monitoring Platform</h1>
      <section aria-labelledby="status-heading">
        <h2 id="status-heading">Service status</h2>
        <p role="status" className={`status ${status}`}>
          {status === "checking" && "Checking backend and database…"}
          {status === "ready" && "Backend and database are ready."}
          {status === "unavailable" &&
            "Backend or database is unavailable. Retrying automatically…"}
        </p>
        <p>
          This page verifies the local platform connection. Equipment
          monitoring, telemetry ingestion, and alerts are not implemented yet.
        </p>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <PlatformStatus />
  </StrictMode>,
);
