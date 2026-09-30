"""Minimal per-device temperature alert evaluation during telemetry ingestion."""

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import AlertEpisode, AlertState
from app.telemetry_schemas import TelemetryEvent

HIGH_THRESHOLD = Decimal("30")
RECOVERY_THRESHOLD = Decimal("28")
CONSECUTIVE_READINGS = 3
MAX_READING_AGE = timedelta(minutes=5)
MAX_FUTURE_SKEW = timedelta(minutes=1)


def evaluate_accepted_reading(
    session: Session,
    item: TelemetryEvent,
    telemetry_id: int,
    backend_received_at: datetime,
    states: dict[str, AlertState],
) -> None:
    """Advance one device's state only for a new, fresh, in-order reading.

    The ingestion transaction holds an exclusive lock on the device row, which
    serializes updates to this state across concurrent batches.
    """
    event_at = (
        item.measured_at
        if item.measured_at is not None and item.quality.clock == "synchronised"
        else item.gateway_received_at
    )
    if (
        not backend_received_at - MAX_READING_AGE
        <= event_at
        <= (backend_received_at + MAX_FUTURE_SKEW)
    ):
        return

    state = states.get(item.device_id)
    if state is None:
        state = session.get(AlertState, item.device_id)
        if state is None:
            state = AlertState(
                device_id=item.device_id,
                last_event_at=event_at,
                high_streak=0,
                recovery_streak=0,
            )
            session.add(state)
        elif event_at <= state.last_event_at:
            return
        states[item.device_id] = state
    elif event_at <= state.last_event_at:
        return

    state.last_event_at = event_at

    if state.active_episode_id is None:
        state.high_streak = state.high_streak + 1 if item.value > HIGH_THRESHOLD else 0
        if state.high_streak == CONSECUTIVE_READINGS:
            state.high_streak = 0
            episode = AlertEpisode(
                device_id=item.device_id,
                opened_at=event_at,
                opening_telemetry_id=telemetry_id,
            )
            session.add(episode)
            session.flush()
            state.active_episode_id = episode.id
    else:
        state.recovery_streak = (
            state.recovery_streak + 1 if item.value < RECOVERY_THRESHOLD else 0
        )
        if state.recovery_streak == CONSECUTIVE_READINGS:
            state.recovery_streak = 0
            episode = session.get(AlertEpisode, state.active_episode_id)
            episode.resolved_at = event_at
            episode.resolving_telemetry_id = telemetry_id
            state.active_episode_id = None
