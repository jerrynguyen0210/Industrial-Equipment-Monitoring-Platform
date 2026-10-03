"""Telemetry classification, history mapping, and transaction coordination."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import Engine
from sqlalchemy.exc import DataError
from sqlalchemy.orm import Session

from app.alerts.service import evaluate_accepted_reading
from app.db.models import AlertState
from app.devices import repository as device_repository
from app.telemetry import repository
from app.telemetry.schemas import (
    DeviceHistory,
    HistoryPoint,
    TelemetryBatchResponse,
    TelemetryResponseItem,
    ValidatedTelemetryBatch,
)

logger = logging.getLogger("uvicorn.error")
MAX_POINTS = 2000
MAX_RANGE = timedelta(days=7)
MAX_CONNECTED_GAP = timedelta(minutes=2)

# The identity is enforced by uq_telemetry_identity. Receipt times and batch
# metadata describe delivery, so retries may change them without changing the event.
IMMUTABLE_CONTENT_FIELDS = (
    "schema_version",
    "measured_at",
    "device_uptime_ms",
    "metric",
    "value",
    "unit",
    "quality",
)


class GatewayForbiddenError(Exception):
    """The credential maps to an absent or disabled gateway/site."""


class DeviceNotFoundError(Exception):
    """The requested device is not registered."""


class InvalidHistoryRangeError(Exception):
    """History requires an ordered, timezone-aware range of at most seven days."""


def ingest_batch(
    engine: Engine,
    gateway_id: str,
    batch: ValidatedTelemetryBatch,
    batch_id: str,
) -> TelemetryBatchResponse:
    """Commit all accepted rows before exposing any per-item outcome."""
    results = []
    with Session(engine) as session, session.begin():
        # Shared ancestor locks prevent registry changes until commit.
        gateway = repository.lock_gateway_eligibility(session, gateway_id)
        if gateway is None or not all(gateway):
            raise GatewayForbiddenError

        device_ids = {
            item.device_id
            for item in batch.items
            if not isinstance(item, TelemetryResponseItem)
        }
        # Lock devices exclusively in ID order so concurrent batches cannot
        # advance one device's alert cursor at the same time.
        assignments = device_repository.lock_assignments(session, device_ids)
        states: dict[str, AlertState] = {}
        for index, item in enumerate(batch.items):
            if isinstance(item, TelemetryResponseItem):
                results.append(item)
                continue
            identity = {
                "device_id": item.device_id,
                "boot_id": item.boot_id,
                "sequence_number": item.sequence_number,
            }
            assignment = assignments.get(item.device_id)
            reason = None
            if assignment is None:
                reason = "unknown_device"
            elif assignment.gateway_id != gateway_id or not assignment.enabled:
                # Disabled devices revoke this gateway's ingestion eligibility.
                reason = "wrong_gateway"
            if reason:
                results.append(
                    TelemetryResponseItem(**identity, outcome="rejected", reason=reason)
                )
                continue

            values = item.model_dump() | {"schema_version": batch.schema_version}
            try:
                # A data representation error in one item must not poison its peers.
                inserted = repository.insert_event(session, values)
            except DataError:
                results.append(
                    TelemetryResponseItem(
                        **identity, outcome="rejected", reason="malformed_value"
                    )
                )
                continue

            outcome = "accepted"
            if inserted is None:
                existing = repository.read_existing_event(session, identity)
                matches = all(
                    getattr(existing, field) == values[field]
                    for field in IMMUTABLE_CONTENT_FIELDS
                )
                outcome = "duplicate" if matches else "rejected"
                if not matches:
                    reason = "identity_conflict"
                    logger.info(
                        "telemetry_identity_conflict",
                        extra={"batch_id": batch_id, "item_index": index},
                    )
            else:
                evaluate_accepted_reading(
                    session, item, inserted.id, inserted.backend_received_at, states
                )
                # A gateway may forward queued readings long after an ESP32
                # disconnects. Only recent gateway contact counts as presence.
                received_age = inserted.backend_received_at - item.gateway_received_at
                if timedelta(0) <= received_age <= timedelta(seconds=90):
                    device_repository.record_presence(session, item.device_id)
            results.append(
                TelemetryResponseItem(
                    **identity,
                    outcome=outcome,
                    **({"reason": reason} if reason else {}),
                )
            )

    # Exiting session.begin() commits. No result can escape if commit fails.
    return TelemetryBatchResponse(batch_id=batch_id, results=results)


def read_device_history(
    engine: Engine, device_id: str, range_start: datetime, range_end: datetime
) -> DeviceHistory:
    if (
        range_start.tzinfo is None
        or range_end.tzinfo is None
        or range_start >= range_end
        or range_end - range_start > MAX_RANGE
    ):
        raise InvalidHistoryRangeError
    with Session(engine) as session:
        if not device_repository.device_exists(session, device_id):
            raise DeviceNotFoundError
        rows = repository.read_history_rows(
            session, device_id, range_start, range_end, MAX_POINTS + 1
        )

    truncated = len(rows) > MAX_POINTS
    ordered = list(reversed(rows[:MAX_POINTS]))
    points: list[HistoryPoint] = []
    previous = None
    for row in ordered:
        timestamp_source = (
            "measured_at"
            if row.measured_at is not None and row.clock_quality == "synchronised"
            else "gateway_received_at"
        )
        gap_before = (
            previous is None
            or row.boot_id != previous.boot_id
            or row.sequence_number != previous.sequence_number + 1
            or row.event_at - previous.event_at > MAX_CONNECTED_GAP
            or (
                (timestamp_source == "measured_at")
                != (
                    previous.measured_at is not None
                    and previous.clock_quality == "synchronised"
                )
            )
        )
        points.append(
            HistoryPoint(
                event_at=row.event_at,
                timestamp_source=timestamp_source,
                measured_at=row.measured_at,
                gateway_received_at=row.gateway_received_at,
                clock_quality=row.clock_quality,
                value=row.value,
                unit=row.unit,
                gap_before=gap_before,
            )
        )
        previous = row

    return DeviceHistory(
        device_id=device_id,
        unit="celsius",
        range_start=range_start,
        range_end=range_end,
        truncated=truncated,
        points=points,
    )
