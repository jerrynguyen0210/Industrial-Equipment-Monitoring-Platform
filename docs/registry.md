# Minimum equipment registry

The registry stores the ownership chain needed by telemetry validation:
`sites` -> `gateways` -> `devices`. It contains no readings, credentials, users,
or HTTP endpoints. The backend [setup commands](../backend/README.md#registry-migrations-and-demo-seed)
apply its Alembic migration and explicitly seed the demo hierarchy.

## Schema and identifiers

| Table | Primary key | Parent | Other required columns |
| --- | --- | --- | --- |
| `sites` | `site_id VARCHAR(128)` | None | `name VARCHAR(200)`, `enabled BOOLEAN DEFAULT true` |
| `gateways` | `gateway_id VARCHAR(128)` | `site_id` references `sites.site_id` | `name VARCHAR(200)`, `enabled BOOLEAN DEFAULT true` |
| `devices` | `device_id VARCHAR(128)` | `gateway_id` references `gateways.gateway_id` | `name VARCHAR(200)`, `enabled BOOLEAN DEFAULT true` |

Identifiers are nonempty, case-sensitive strings with a registry storage limit
of 128 characters. They are stored and compared exactly, without trimming or
case folding. Provisioning must use stable IDs. The limit is a registry choice;
it does not change the approved telemetry envelope or freeze additional wire
validation rules. `device_id` is globally unique, including across gateways.
PostgreSQL primary keys enforce uniqueness atomically under concurrent writes.

Every gateway has exactly one site and every device has exactly one gateway.
Device site membership is derived through its gateway, avoiding a redundant
site field that could disagree. Foreign keys use `ON DELETE RESTRICT`, and both
parent-reference columns are indexed. SQLAlchemy exposes relationships in both
directions. Disable an entity to suspend eligibility while preserving identity;
deleting a parent with children is rejected, with no cascading row deletion.

## Ownership checks

`app.registry.check_device_ownership(session, device_id=..., gateway_id=...)`
queries the device, its assigned gateway, and the gateway's site in one query:

| Result | Meaning |
| --- | --- |
| `allowed` | The device belongs to the supplied gateway and all three records are enabled. |
| `unknown_device` | The device is not registered. |
| `wrong_gateway` | The registered device belongs to a different gateway. |
| `disabled` | Ownership matches, but the device, gateway, or site is disabled. |

Unknown device takes precedence over assignment; a wrong gateway takes precedence
over enabled-state checks. The caller must derive `gateway_id` from authenticated
credentials. Supplied payload IDs cannot authenticate a caller. This follows
section 6 of the [approved ingestion contract](Technical_Lead_Telemetry_Ingestion_Contract_Approval_Sprint01.pdf).
`disabled` is an internal registry result; mapping it into an ingestion response
remains part of the future authentication/ingestion workstream. No new public
telemetry error code is introduced here.

Callers own the SQLAlchemy session and transaction. The lookup observes state at
query time, does not reserve ownership against concurrent reassignments, and does
not commit or acknowledge telemetry. An ingestion implementation must define
transaction coordination if assignment or enabled state can change during a write.

## Migration and deployment

Revision `0001_registry` creates sites, then gateways, then devices and indexes.
Alembic uses `app.config.database_conninfo()` through the SQLAlchemy engine:
nonempty `DATABASE_URL` wins; otherwise all five `PG*` settings are required.
SSL and other libpq URL options are retained; SQLAlchemy sessions enforce UTC for
[telemetry storage](telemetry-storage.md). Connection timeout is three seconds;
statement and lock timeouts are five seconds. The pool allows up to five
connections with a five-second checkout timeout. Credentials are absent from
`alembic.ini`, the engine URL, and committed files.

The backend image includes Alembic and migration sources. Its Docker build
allowlist still excludes local environment files and secrets. Compose startup
continues to start the health API with one command. Run `alembic upgrade head`
as a separate deployment step, followed by the seed only when demo data is wanted.
Do not run competing migrations from multiple API processes. The local database
owner remains a development convenience; deployed migration and application roles
must be provisioned separately with appropriate privileges.

Downgrade of `0001_registry` drops devices, gateways, then sites. A downgrade from
the current head to `base` first removes telemetry in `0002_telemetry`.
It destroys registry data and is tested only in a disposable database. For an
existing environment, stop registry and telemetry writers and take a PostgreSQL
backup before downgrade. If a schema operation
fails, PostgreSQL transactional DDL rolls it back; inspect `alembic current`
before retrying. After a completed destructive downgrade, recover data from the
backup into a separate database and validate it before switching consumers;
`upgrade head` alone restores only the schema. Demo seeding cannot restore real
registrations. The initial revision must not be stamped onto unrelated existing
tables or used as an automatic repair operation.

## Demo seed

`python -m app.seed` commits one enabled hierarchy on a clean migrated database:

| Entity | ID | Name |
| --- | --- | --- |
| Site | `site-demo-001` | Demo site |
| Gateway | `gateway-demo-001` | Demo gateway |
| Device | `device-demo-001` | Demo device |

The seed inserts missing IDs and preserves existing names and enabled states.
PostgreSQL conflict handling and row locks allow concurrent seed runs. A demo
gateway already assigned to another site, or demo device assigned to another
gateway, raises a conflict and rolls back all new rows in that seed transaction.
No automatic reassignment or re-enabling occurs. Success is printed only after
commit. Seed data is separate from schema migration, so ordinary deployments do
not receive demo registrations accidentally.

## Verification

The [PostgreSQL integration suite](../backend/tests/integration/test_registry.py)
creates a fresh database on an explicitly selected test server and removes only
that database after testing. It tests migration up/down/up with populated tables,
Alembic model agreement, duplicate IDs within/across gateways and concurrent
registration, database defaults/required values, parent restrictions, enabled
states, seed repeatability/concurrency/conflict rollback, and CLI entry points.
It fails when its explicit test configuration is missing. CI provisions PostgreSQL
17 and runs this suite separately from database-free unit tests.

The [Compose smoke suite](../tests/compose_smoke.py) also runs the packaged
migration and seed, then checks that the linked records survive a full stack
down/up using the existing PostgreSQL volume. Readiness continues to test
connectivity only; it does not certify migration currency or registry eligibility.

Local acceptance evidence on 2026-09-24: 13 unit tests and 11 integration tests
passed on Python 3.14 with PostgreSQL 17.11. Ruff lint/format checks, dependency
consistency, offline migration SQL generation, and Alembic model agreement passed.
The explicitly seeded local demo database retained exactly one enabled site,
gateway, and device after a PostgreSQL restart. Docker was unavailable locally,
so the updated Compose smoke suite and container build were not run here. The CI
configuration uses Python 3.13 and PostgreSQL 17; a CI run is separate evidence.

Docker follow-up on 2026-09-25: Compose configuration validation, both image
builds, and all six isolated Compose smoke checkpoints passed on Docker Desktop
4.92.0 / Engine 29.8.0 / Compose 5.5.1 in Linux container mode. All 11 registry
integration tests also passed inside the actual backend image with Python 3.13.15
and PostgreSQL 17.11. Manual health/proxy checks passed; the seeded ownership
chain contained exactly one enabled site/gateway/device, and a duplicate device
insert was rejected by `pk_devices` without changing the original row. These are
local Docker results, not a GitHub Actions run. The verified PowerShell commands
are in the [Windows Docker testing guide](docker-testing.md).

Implementation references: [SQLAlchemy engine configuration](https://docs.sqlalchemy.org/en/20/core/engines.html)
and [Alembic connection sharing](https://alembic.sqlalchemy.org/en/latest/cookbook.html#sharing-a-connection-across-one-or-more-programmatic-migration-commands).
