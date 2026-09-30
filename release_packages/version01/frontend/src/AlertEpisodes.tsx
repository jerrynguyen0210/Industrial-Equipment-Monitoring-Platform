import { useEffect, useState } from "react";
import { getAlerts, type AlertEpisode, type AlertEpisodeList } from "./api";

const refreshIntervalMs = 5000;

function formatTimestamp(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    timeZoneName: "short",
  }).format(new Date(value));
}

function EpisodeCard({ episode }: { episode: AlertEpisode }) {
  const state = episode.state === "active" ? "ACTIVE" : "RESOLVED";
  return (
    <article
      className={`alert-episode-card alert-episode-${episode.state}`}
      aria-label={`${state} high temperature alert for ${episode.device_id}`}
    >
      <div className="alert-episode-heading">
        <div>
          <h3>High temperature · {episode.device_name}</h3>
          <p className="device-id">{episode.device_id}</p>
        </div>
        <span className={`alert-state alert-state-${episode.state}`}>
          {state}
        </span>
      </div>

      <dl className="alert-episode-details">
        <div>
          <dt>Alert triggered</dt>
          <dd>{formatTimestamp(episode.opened_at)}</dd>
        </div>
        <div>
          <dt>Triggering reading</dt>
          <dd>{episode.opening_value} °C</dd>
        </div>
        {episode.resolved_at && (
          <div>
            <dt>Recovered</dt>
            <dd>{formatTimestamp(episode.resolved_at)}</dd>
          </div>
        )}
        {episode.resolving_value !== null && (
          <div>
            <dt>Recovery reading</dt>
            <dd>{episode.resolving_value} °C</dd>
          </div>
        )}
      </dl>
    </article>
  );
}

export function AlertEpisodes() {
  const [alerts, setAlerts] = useState<AlertEpisodeList | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    let request: AbortController;

    async function refresh() {
      request = new AbortController();
      const timeout = setTimeout(() => request.abort(), 6000);
      try {
        const result = await getAlerts(request.signal);
        if (!stopped) {
          setAlerts(result);
          setError(false);
        }
      } catch {
        if (!stopped) setError(true);
      } finally {
        clearTimeout(timeout);
        if (!stopped) {
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
  }, []);

  const rule = alerts?.rule;

  return (
    <section
      className="panel alert-demo-panel"
      aria-labelledby="alerts-heading"
    >
      <div className="section-heading">
        <div>
          <p className="eyebrow">Alert workflow</p>
          <h2 id="alerts-heading">Temperature alert episodes</h2>
        </div>
        {alerts && (
          <span className="demo-data-badge">{alerts.active_count} active</span>
        )}
      </div>

      {rule && (
        <p className="alert-demo-description">
          {rule.consecutive_readings} consecutive readings above{" "}
          {rule.high_threshold} °C open an episode. {rule.consecutive_readings}{" "}
          consecutive readings below {rule.recovery_threshold} °C resolve it.
        </p>
      )}

      {error && (
        <p className="equipment-error" role="alert">
          Alert episodes could not be loaded. Check the backend connection.
        </p>
      )}
      {!alerts && !error && (
        <p className="equipment-message" role="status">
          Loading alert episodes…
        </p>
      )}
      {alerts && alerts.episodes.length === 0 && (
        <p className="equipment-message">No temperature alerts recorded.</p>
      )}
      {alerts?.episodes.map((episode) => (
        <EpisodeCard key={episode.id} episode={episode} />
      ))}
    </section>
  );
}
