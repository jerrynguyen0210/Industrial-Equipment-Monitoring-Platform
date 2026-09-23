# Shared Tests

Tests and fixtures that validate integration across workstreams.

## Planned contents

- Contract tests for telemetry and API boundaries.
- Integration tests for device/simulator, gateway, and backend interactions.
- End-to-end monitoring workflows and shared fixtures.

Workstream unit tests belong with the implementation they exercise. Add shared
test subdirectories here as suites are introduced.

## Setup and validation

TODO: Select runners and document dependencies, environment setup, test commands,
and cleanup. No shared test runner or suite is configured yet.

Use repeatable simulator scenarios where possible and keep fixture data free of
secrets. Follow the shared [conventions](../CONTRIBUTING.md).
