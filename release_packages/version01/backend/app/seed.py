"""Explicit, transactional demo registry seed: python -m app.seed."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import create_database_engine
from app.models import Device, Gateway, Site

SITE_ID = "site-demo-001"
GATEWAY_ID = "gateway-demo-001"
DEVICE_ID = "device-demo-001"


class SeedConflictError(RuntimeError):
    """A demo identifier is already assigned to a different parent."""


def seed_registry(session: Session) -> None:
    """Insert missing demo records; the caller commits or rolls back the whole seed.

    Existing names and enabled states are preserved. Unique constraints handle
    concurrent seed runs; row locks stabilize the parent checks until commit.
    """
    session.execute(
        insert(Site)
        .values(site_id=SITE_ID, name="Demo site")
        .on_conflict_do_nothing(index_elements=[Site.site_id])
    )
    session.execute(
        select(Site.site_id).where(Site.site_id == SITE_ID).with_for_update()
    ).scalar_one()
    session.execute(
        insert(Gateway)
        .values(gateway_id=GATEWAY_ID, site_id=SITE_ID, name="Demo gateway")
        .on_conflict_do_nothing(index_elements=[Gateway.gateway_id])
    )
    parent_site = session.execute(
        select(Gateway.site_id)
        .where(Gateway.gateway_id == GATEWAY_ID)
        .with_for_update()
    ).scalar_one()
    if parent_site != SITE_ID:
        raise SeedConflictError("Demo gateway belongs to a different site")
    session.execute(
        insert(Device)
        .values(device_id=DEVICE_ID, gateway_id=GATEWAY_ID, name="Demo device")
        .on_conflict_do_nothing(index_elements=[Device.device_id])
    )
    parent_gateway = session.execute(
        select(Device.gateway_id).where(Device.device_id == DEVICE_ID).with_for_update()
    ).scalar_one()
    if parent_gateway != GATEWAY_ID:
        raise SeedConflictError("Demo device belongs to a different gateway")


def main() -> None:
    engine = create_database_engine()
    try:
        with Session(engine) as session, session.begin():
            seed_registry(session)
    except SeedConflictError as error:
        raise SystemExit(str(error)) from None
    except SQLAlchemyError:
        # Driver exceptions can include connection details; keep CLI output safe.
        raise SystemExit(
            "Registry seed failed; check database access and run Alembic upgrade head"
        ) from None
    finally:
        engine.dispose()
    print(f"Demo registry committed: {SITE_ID} -> {GATEWAY_ID} -> {DEVICE_ID}")


if __name__ == "__main__":
    main()
