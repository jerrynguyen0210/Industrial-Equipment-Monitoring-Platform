# Shared testing coding conventions

Follow [CONTRIBUTING.md](../CONTRIBUTING.md) and these test rules.

## Test design

- Put component unit tests with the component; use `tests/` for shared contracts
  and end-to-end behavior.
- Give each test one observable behavior and a descriptive name.
- Keep fixtures minimal, versioned, deterministic, and free of secrets.
- Use unique IDs, ports, database names, and project names for parallel isolation.
- Control time and randomness; never rely on test execution order.

## Contract and reliability coverage

- Assert exact identities, fields, ordering, status codes, and rejection reasons.
- Cover duplicate replay, changed-content conflict, invalid values, ownership,
  mixed batches, null time, and out-of-order arrival.
- Test failures at durability boundaries: broker, gateway queue, HTTP response,
  transaction commit, database outage, restart, and recovery.
- Verify rejected data is absent and retries do not mutate accepted rows.
- Distinguish mocked/unit evidence from real container or hardware evidence.

## Cleanup and reporting

- Create only test-owned resources and remove only those resources in cleanup.
- Preserve bounded diagnostics on failure without printing credentials or full
  sensitive payloads.
- Use finite timeouts and fail a skipped required check.
- Report exact commands, versions, outcomes, and any untested boundary.

## Validation checklist

- [ ] Tests pass alone, together, and in CI order.
- [ ] Repeated and parallel runs do not collide.
- [ ] Failure paths return nonzero and retain useful diagnostics.
- [ ] Cleanup also runs after ordinary failure.
- [ ] Acceptance claims match the environment actually exercised.
