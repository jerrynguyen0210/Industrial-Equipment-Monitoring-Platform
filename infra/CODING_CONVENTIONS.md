# Infrastructure Coding Conventions

Development rules for environment configuration, provisioning, deployment,
automation, and recovery. These are implementation expectations; no deployment
tooling or automated infrastructure checks are currently configured.

## 1. Scope and shared rules

- Follow [CONTRIBUTING.md](../CONTRIBUTING.md) for issues, branches, commits, and
  pull requests, and [.editorconfig](../.editorconfig) for file formatting.
- Keep supported tool versions and provisioning, validation, deployment, and
  teardown commands in [README.md](README.md). Put operational runbooks in `docs/`.
- Follow the [project reference documents](../docs/README.md#project-reference-documents)
  for reliability, security, and deployment requirements. This guide does not
  finalize proposed tools or unresolved durability settings.
- Document environment ownership, purpose, resource limits, and cost expectations
  before adding hosted resources.

## 2. Configuration and automation style

- Store reproducible environment definitions in version control. Prefer
  declarative configuration; keep imperative scripts small and focused.
- Use consistent names for services, volumes, networks, and environment variables.
  Name timeout and capacity settings with their units.
- Validate required inputs before making changes. Fail with an actionable error
  and a nonzero exit code instead of continuing after a failed command.
- Quote paths and values correctly, including paths with spaces. Do not construct
  shell commands from untrusted input or log commands containing secret values.
- Make repeated provisioning converge on the intended state. Document any step
  that is not repeatable or that changes persistent application data.
- Keep environment differences explicit and small. Document precedence among
  defaults, environment files, deployment variables, and runtime overrides.
- Add formatters and configuration validators with the selected tools. Comment
  on operational constraints and link deferred work to issues.

## 3. Environment and failure boundaries

- Separate development, test, and deployed resources, credentials, and state.
  Test defaults must not point to operational databases or device brokers.
- Preserve the local acquisition boundary: stopping the backend must not also stop
  local MQTT or erase the gateway queue. Document independent service lifecycles.
- Declare ports, network access, dependencies, and persistent volumes explicitly.
  Do not expose storage or administration ports publicly by default.
- Keep durable database and gateway queue data outside disposable process or
  container filesystems. Document volume ownership and permissions.
- Use readiness checks for dependency availability and liveness checks for process
  health. Startup order alone is not proof that a dependency is ready.
- Bound CPU, memory, disk, connection, and log usage. Configure restart and shutdown
  behavior so outages do not produce uncontrolled restart loops or lost work.
- If infrastructure state is introduced, protect it with restricted access,
  appropriate locking, and recovery procedures. Treat it as potentially sensitive.

## 4. Artifacts and dependency control

- Pin tools and dependencies through version declarations and lockfiles. Use
  identifiable immutable release artifacts; avoid mutable `latest` deployments.
- Build an artifact once and promote that tested artifact between environments.
  Record the source revision, build configuration, and artifact identifier.
- Keep credentials out of build contexts, image layers, caches, and artifacts.
  Exclude local environment files and generated state from version control.
- For containers, use a minimal supported runtime image and an unprivileged user
  where practical. Document any required elevated access to hardware or files.
- Review dependency and image findings before release. Record assessment and
  mitigation for unresolved findings rather than silently ignoring scanner output.

## 5. Secrets and network security

- Inject secrets through the chosen environment's protected mechanism. Commit
  sanitized examples listing required names and meanings, never working values.
- Use separate revocable credentials for gateways and least-privilege accounts
  for services, deployment automation, and databases.
- Use HTTPS for deployed web/API traffic and authenticated TLS for device MQTT.
  Document certificate issuance, renewal, trust, and expiry monitoring.
- Restrict device topic permissions and service network access to required paths.
  Test that unauthenticated clients and untrusted certificates are rejected.
- Document secret rotation without data loss. Redact logs, diagnostic bundles,
  plan output, and CI artifacts that could disclose credentials or state.
- Keep privileged automation isolated from untrusted pull-request code. Scope CI
  tokens to required permissions and protect deployment credentials.

## 6. Deployment and database changes

- Review the planned resource or configuration changes before applying them.
  Identify the target environment, affected services, downtime, and data impact.
- Document deployment ordering for schema changes, application versions, and
  workers. Prevent multiple instances from racing to apply the same migration.
- Use compatible staged migrations where possible. Separate destructive cleanup
  from the initial rollout so recovery remains practical.
- Define health checks, smoke checks, and rollout stop conditions before release.
  Verify the user-facing workflow and telemetry path after deployment.
- Record how to restore the previous application artifact or recover forward.
  An application rollback does not automatically reverse a database migration.
- Serialize deployments targeting the same environment. Make interrupted or
  partially completed operations observable and recoverable.
- Require an explicit target for destructive teardown or reset commands. Scope
  them to owned resources and distinguish service shutdown from deleting data.

## 7. Backup, retention, and recovery

- Implement and document the agreed backup schedule, retention, and recovery
  targets. Keep backup access separate from routine application permissions.
- Test restoration into a clean, isolated environment. Verify records and service
  behavior; a successful backup upload alone is not recovery evidence.
- Record backup time, restore duration, software versions, and any data loss window.
  Distinguish restore-test results from untested objectives.
- Protect gateway queue data during maintenance and host replacement. Document
  the limits of the recovery guarantee and any manual reconciliation procedure.
- Coordinate telemetry retention with backend jobs and registry preservation.
  Avoid unrelated infrastructure cleanup deleting retained application data.
- Keep recovery instructions executable by another developer and explicit about
  secrets, artifact versions, storage paths, and required access.

## 8. Observability and operational validation

- Collect service health, resource usage, queue depth and age, ingestion failures,
  and backup results. Bound log retention and metric cardinality.
- Give actionable alerts an owner and a runbook. Distinguish edge intake problems,
  backend outages, authentication failures, and storage pressure.
- Validate configuration and plans without changing deployed resources where
  possible. Exercise deploy and teardown in disposable environments.
- Test a clean-checkout setup, independent backend outage, gateway persistence,
  credential revocation, storage exhaustion, and restore procedure as relevant.
- Keep infrastructure-specific checks in `infra/` and shared operational scenarios
  in [tests/](../tests/README.md).
- Record exact commands and results once tooling exists. Do not imply that CI,
  branch protection, scheduled backups, or deployment gates are already enabled.

## 9. Pull request checklist

- [ ] The issue, target environment, resource changes, and data impact are clear.
- [ ] Applicable formatting, configuration validation, and plan checks pass.
- [ ] Secrets, permissions, network exposure, and persistent storage were reviewed.
- [ ] Deployment order, health checks, and rollback or recovery steps are documented.
- [ ] Clean setup and relevant outage or restore scenarios were verified.
- [ ] Runbooks, configuration examples, and validation limitations are updated.

Mark items that do not apply. Record significant exceptions in the pull request
and shared interface or architecture changes in `docs/`.
