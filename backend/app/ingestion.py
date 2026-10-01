"""Transactional telemetry classification with PostgreSQL-authoritative identity."""

import logging
from datetime import timedelta

from sqlalchemy import Engine, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DataError
from sqlalchemy.orm import Session

from app.alerting import evaluate_accepted_reading
from app.models import AlertState, Device, Gateway, Site, Telemetry
from app.telemetry_schemas import TelemetryBatchResponse, TelemetryResponseItem
from app.telemetry_validation import ValidatedTelemetryBatch

logger = logging.getLogger("uvicorn.error")

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
        gateway = session.execute(
            select(Gateway.enabled, Site.enabled)
            .join(Gateway.site)
            .where(Gateway.gateway_id == gateway_id)
            .with_for_update(read=True, of=(Gateway, Site))
        ).one_or_none()
        if gateway is None or not all(gateway):
            raise GatewayForbiddenError

        device_ids = {
            item.device_id
            for item in batch.items
            if not isinstance(item, TelemetryResponseItem)
        }
        # Lock devices exclusively in ID order so concurrent batches cannot
        # advance one device's alert cursor at the same time.
        assignments = {
            row.device_id: row
            for row in session.execute(
                select(Device.device_id, Device.gateway_id, Device.enabled)
                .where(Device.device_id.in_(device_ids))
                .order_by(Device.device_id)
                .with_for_update()
            )
        }
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
                with session.begin_nested():
                    inserted = session.execute(
                        insert(Telemetry)
                        .values(**values)
                        .on_conflict_do_nothing(constraint="uq_telemetry_identity")
                        .returning(Telemetry.id, Telemetry.backend_received_at)
                    ).one_or_none()
            except DataError:
                results.append(
                    TelemetryResponseItem(
                        **identity, outcome="rejected", reason="malformed_value"
                    )
                )
                continue

            outcome = "accepted"
            if inserted is None:
                existing = session.execute(
                    select(Telemetry).filter_by(**identity).with_for_update(read=True)
                ).scalar_one()
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
                    session.execute(
                        update(Device)
                        .where(Device.device_id == item.device_id)
                        .values(last_seen_at=func.clock_timestamp())
                    )
            results.append(
                TelemetryResponseItem(
                    **identity,
                    outcome=outcome,
                    **({"reason": reason} if reason else {}),
                )
            )

    # Exiting session.begin() commits. No result can escape if commit fails.
    return TelemetryBatchResponse(batch_id=batch_id, results=results)
