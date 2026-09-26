import { useState } from "react";

const alertThreshold = 80;
const readingsToTrigger = 3;

type TelemetryEvent = {
  deviceId: string;
  bootId: string;
  sequenceNumber: number;
  value: number;
  measuredAt: string;
};

type AlertEpisode = {
  id: string;
  deviceId: string;
  state: "ACTIVE" | "RESOLVED";
  startedAt: string;
  triggeredAt: string;
  updatedAt: string;
  resolvedAt: string | null;
  highReadingCount: number;
};

type DemoState = {
  episode: AlertEpisode | null;
  seenTelemetry: Set<string>;
  highReadings: TelemetryEvent[];
  duplicateCount: number;
};

function telemetryIdentity(event: TelemetryEvent): string {
  return `${event.deviceId}:${event.bootId}:${event.sequenceNumber}`;
}

function receiveTelemetry(state: DemoState, event: TelemetryEvent): DemoState {
  const identity = telemetryIdentity(event);
  if (state.seenTelemetry.has(identity)) {
    return { ...state, duplicateCount: state.duplicateCount + 1 };
  }

  const seenTelemetry = new Set(state.seenTelemetry).add(identity);
  if (event.value >= alertThreshold) {
    const highReadings = [...state.highReadings, event];
    if (state.episode?.state === "ACTIVE") {
      return {
        ...state,
        seenTelemetry,
        highReadings,
        episode: {
          ...state.episode,
          updatedAt: event.measuredAt,
          highReadingCount: state.episode.highReadingCount + 1,
        },
      };
    }

    if (highReadings.length >= readingsToTrigger) {
      const triggerReadings = highReadings.slice(-readingsToTrigger);
      return {
        ...state,
        seenTelemetry,
        highReadings,
        episode: {
          id: telemetryIdentity(triggerReadings[0]),
          deviceId: event.deviceId,
          state: "ACTIVE",
          startedAt: triggerReadings[0].measuredAt,
          triggeredAt: event.measuredAt,
          updatedAt: event.measuredAt,
          resolvedAt: null,
          highReadingCount: readingsToTrigger,
        },
      };
    }

    return { ...state, seenTelemetry, highReadings };
  }

  const highReadings =
    state.episode?.state === "ACTIVE" ? [] : state.highReadings;
  return {
    ...state,
    seenTelemetry,
    highReadings,
    episode:
      state.episode?.state === "ACTIVE"
        ? {
            ...state.episode,
            state: "RESOLVED",
            updatedAt: event.measuredAt,
            resolvedAt: event.measuredAt,
          }
        : state.episode,
  };
}

function createDemoState(): DemoState {
  const now = Date.now();
  const timestamp = (minutesAgo: number) =>
    new Date(now - minutesAgo * 60_000).toISOString();
  const firstHigh: TelemetryEvent = {
    deviceId: "device-demo-001",
    bootId: "demo-boot-01",
    sequenceNumber: 41,
    value: 82.4,
    measuredAt: timestamp(4),
  };
  const secondHigh: TelemetryEvent = {
    ...firstHigh,
    sequenceNumber: 42,
    value: 84.1,
    measuredAt: timestamp(3),
  };
  const thirdHigh: TelemetryEvent = {
    ...firstHigh,
    sequenceNumber: 43,
    value: 86.2,
    measuredAt: timestamp(2),
  };
  const initialState: DemoState = {
    episode: null,
    seenTelemetry: new Set(),
    highReadings: [],
    duplicateCount: 0,
  };

  return [firstHigh, secondHigh, thirdHigh, thirdHigh].reduce(
    receiveTelemetry,
    initialState,
  );
}

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

export function AlertEpisodes() {
  const [demoState, setDemoState] = useState(createDemoState);
  const episode = demoState.episode;

  function simulateRecovery() {
    if (!episode || episode.state !== "ACTIVE") return;
    setDemoState((state) =>
      receiveTelemetry(state, {
        deviceId: episode.deviceId,
        bootId: "demo-boot-01",
        sequenceNumber: 44,
        value: 76.8,
        measuredAt: new Date().toISOString(),
      }),
    );
  }

  function replayDuplicate() {
    if (!episode) return;
    const duplicate: TelemetryEvent = {
      deviceId: episode.deviceId,
      bootId: "demo-boot-01",
      sequenceNumber: 43,
      value: 86.2,
      measuredAt: new Date(episode.triggeredAt).toISOString(),
    };
    setDemoState((state) => receiveTelemetry(state, duplicate));
  }

  return (
    <section
      className="panel alert-demo-panel"
      aria-labelledby="alerts-heading"
    >
      <div className="section-heading">
        <div>
          <p className="eyebrow">Alert workflow · demo data</p>
          <h2 id="alerts-heading">Temperature alert episodes</h2>
        </div>
        <span className="demo-data-badge">Sample only</span>
      </div>

      <p className="alert-demo-description">
        Three consecutive readings at or above {alertThreshold} °C create one
        episode. A reading below the threshold resolves that episode.
      </p>

      {episode ? (
        <article
          className={`alert-episode-card alert-episode-${episode.state.toLowerCase()}`}
          aria-label={`${episode.state} high temperature alert for ${episode.deviceId}`}
        >
          <div className="alert-episode-heading">
            <div>
              <h3>High temperature</h3>
              <p className="device-id">{episode.deviceId}</p>
            </div>
            <span
              className={`alert-state alert-state-${episode.state.toLowerCase()}`}
            >
              {episode.state}
            </span>
          </div>

          <dl className="alert-episode-details">
            <div>
              <dt>Threshold</dt>
              <dd>
                ≥ {alertThreshold} °C for {readingsToTrigger} readings
              </dd>
            </div>
            <div>
              <dt>High readings</dt>
              <dd>{episode.highReadingCount} in this episode</dd>
            </div>
            <div>
              <dt>Episode started</dt>
              <dd>{formatTimestamp(episode.startedAt)}</dd>
            </div>
            <div>
              <dt>Alert triggered</dt>
              <dd>{formatTimestamp(episode.triggeredAt)}</dd>
            </div>
            {episode.resolvedAt && (
              <div>
                <dt>Recovered</dt>
                <dd>{formatTimestamp(episode.resolvedAt)}</dd>
              </div>
            )}
          </dl>

          <div className="alert-demo-actions">
            <button
              className="refresh-button"
              type="button"
              onClick={replayDuplicate}
            >
              Replay duplicate reading
            </button>
            {episode.state === "ACTIVE" ? (
              <button
                className="recovery-button"
                type="button"
                onClick={simulateRecovery}
              >
                Simulate recovery
              </button>
            ) : (
              <span className="alert-recovery-note">Same episode resolved</span>
            )}
          </div>
          <p className="alert-demo-feedback" role="status" aria-live="polite">
            {demoState.duplicateCount > 0
              ? `Duplicate telemetry ignored · ${demoState.duplicateCount} duplicate${demoState.duplicateCount === 1 ? "" : "s"} ignored · one episode card.`
              : "Duplicate sample telemetry is ignored by its device, boot, and sequence identity."}
          </p>
        </article>
      ) : (
        <p className="equipment-message">No sample alert episode is active.</p>
      )}
    </section>
  );
}
