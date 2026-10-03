"""Temperature alert evaluation and persisted episode read models."""

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, aliased

from app.alerts.schemas import AlertEpisodeList, AlertEpisodeStatus, AlertRule
from app.db.models import AlertEpisode, AlertState, Device, Telemetry
from app.telemetry.schemas import TelemetryEvent

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


def list_alert_episodes(engine: Engine, limit: int) -> AlertEpisodeList:
    """Return active episodes first, then the most recently opened ones."""
    opening = aliased(Telemetry)
    resolving = aliased(Telemetry)
    statement = (
        select(
            AlertEpisode.id,
            AlertEpisode.device_id,
            Device.name.label("device_name"),
            AlertEpisode.opened_at,
            AlertEpisode.resolved_at,
            opening.value.label("opening_value"),
            resolving.value.label("resolving_value"),
        )
        .join(Device, Device.device_id == AlertEpisode.device_id)
        .join(opening, opening.id == AlertEpisode.opening_telemetry_id)
        .outerjoin(resolving, resolving.id == AlertEpisode.resolving_telemetry_id)
        .order_by(
            AlertEpisode.resolved_at.is_(None).desc(),
            AlertEpisode.opened_at.desc(),
            AlertEpisode.id.desc(),
        )
        .limit(limit)
    )
    active = select(func.count()).where(AlertEpisode.resolved_at.is_(None))

    with Session(engine) as session:
        rows = session.execute(statement).all()
        active_count = session.execute(active).scalar_one()

    return AlertEpisodeList(
        rule=AlertRule(
            high_threshold=HIGH_THRESHOLD,
            recovery_threshold=RECOVERY_THRESHOLD,
            consecutive_readings=CONSECUTIVE_READINGS,
            unit="celsius",
        ),
        active_count=active_count,
        episodes=[
            AlertEpisodeStatus(
                id=row.id,
                device_id=row.device_id,
                device_name=row.device_name,
                state="active" if row.resolved_at is None else "resolved",
                opened_at=row.opened_at,
                opening_value=row.opening_value,
                resolved_at=row.resolved_at,
                resolving_value=row.resolving_value,
            )
            for row in rows
        ],
    )
