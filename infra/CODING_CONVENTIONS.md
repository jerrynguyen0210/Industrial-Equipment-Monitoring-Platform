# Infrastructure coding conventions

Follow [CONTRIBUTING.md](../CONTRIBUTING.md) and these infrastructure rules.

## Configuration and automation

- Make scripts repeatable, fail fast, and safe to rerun.
- Validate prerequisites and settings before changing services or data.
- Pin runtime/dependency versions and commit lockfiles or image digests.
- Keep environment-specific values in ignored configuration with sanitized
  examples.
- Never print secrets or render them into build layers and logs.

## Deployment and storage

- Use explicit migrations and one migration owner per environment.
- Keep application, migration, and database administrative roles separate in
  deployed environments.
- Preserve named volumes and gateway queues during normal update/rollback.
- Treat `down --volumes`, database downgrade, and credential replacement as
  destructive operations.
- Define retention and capacity limits before production use.

## Security and operations

- Bind local ports to loopback by default and document every exposed port.
- Require TLS and managed credentials outside a trusted lab network.
- Provide liveness and dependency-aware readiness without secret details.
- Back up off host, encrypt backups, and prove restore in isolation.
- Record version, configuration source, migration head, and validation evidence.

## Validation checklist

- [ ] Shell syntax and Compose configuration pass.
- [ ] Fresh install and safe rerun pass.
- [ ] Upgrade, restart, outage, and rollback paths preserve intended data.
- [ ] Secret/residue scan passes.
- [ ] Backup and restore evidence is current.
