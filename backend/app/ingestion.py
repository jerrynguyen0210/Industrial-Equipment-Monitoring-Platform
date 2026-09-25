"""Transactional telemetry classification with PostgreSQL-authoritative identity."""

import logging

from sqlalchemy import Engine, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DataError
from sqlalchemy.orm import Session

from app.models import Device, Gateway, Site, Telemetry
from app.telemetry_schemas import TelemetryBatchResponse, TelemetryResponseItem
from app.telemetry_validation import ValidatedTelemetryBatch

logger = logging.getLogger("uvicorn.error")


class GatewayForbiddenError(Exception):
    """The credential maps to an absent or disabled gateway/site."""


def ingest_batch(
    engine: Engine,
    gateway_id: str,
    batch: ValidatedTelemetryBatch,
    batch_id: str,
) -> TelemetryBatchResponse:
    results = []
    with Session(engine) as session, session.begin():
        # Shared row locks allow concurrent ingestion while preventing registry
        # reassignment, disabling, or deletion until this transaction commits.
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
        assignments = {
            row.device_id: row
            for row in session.execute(
                select(Device.device_id, Device.gateway_id, Device.enabled)
                .where(Device.device_id.in_(device_ids))
                .order_by(Device.device_id)
                .with_for_update(read=True)
            )
        }
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
                        .returning(Telemetry.id)
                    ).scalar_one_or_none()
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
                    getattr(existing, field) == value
                    for field, value in values.items()
                    if field != "gateway_received_at"
                )
                outcome = "duplicate" if matches else "rejected"
                if not matches:
                    reason = "identity_conflict"
                    logger.info(
                        "telemetry_identity_conflict",
                        extra={"batch_id": batch_id, "item_index": index},
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
