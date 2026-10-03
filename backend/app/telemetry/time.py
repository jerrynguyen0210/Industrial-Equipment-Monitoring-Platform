"""Shared event time rule for telemetry read models."""

from sqlalchemy import case


def event_time(telemetry):
    """Use device time only when its clock is synchronised and it is present."""
    return case(
        (
            (telemetry.measured_at.is_not(None))
            & (telemetry.quality["clock"].astext == "synchronised"),
            telemetry.measured_at,
        ),
        else_=telemetry.gateway_received_at,
    )
