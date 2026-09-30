# Contributing

## Issues and task IDs

GitHub Issues are the source of truth for planned work. Use the task issue
template to record the workstream, scope, acceptance criteria, and validation.

- An issue's canonical ID is `IEMP-<GitHub issue number>`, for example `IEMP-42`
  for GitHub issue `#42`. Do not allocate a separate number sequence.
- Create an issue with a descriptive title, for example
  `[gateway] Buffer telemetry during disconnection`. Its ID is known once GitHub
  creates it; the title does not need to repeat the ID.
- For checklist tasks inside an issue, append `-T<number>`, for example
  `IEMP-42-T1`. Start at `T1` within each issue and never renumber or reuse an ID.
- If a task needs independent tracking, create a linked GitHub issue. It receives
  its own `IEMP-<number>` ID; link it from the original checklist task.
- Use canonical IDs in plans and commit subjects. Include GitHub references such
  as `Refs #42` or `Closes #42` in pull request descriptions so GitHub links them.

Example checklist for issue `#42`:

```markdown
- [ ] IEMP-42-T1: Define the telemetry payload contract.
- [ ] IEMP-42-T2: Implement gateway forwarding.
- [ ] IEMP-42-T3: Verify forwarding with simulator data.
```

The initial repository bootstrap may omit an issue ID. Subsequent planned work
should use an existing issue.

## Branch convention

`main` is the integration branch. Use short-lived branches and pull requests for
changes. Repository branch protection and CI must be configured separately.

```text
codex/<type>/iemp-<issue-number>-<short-description>
```

Use lowercase words separated by hyphens. Choose a type from the commit types
below. Keep a branch focused on one issue; checklist tasks can share that branch.

Examples:

```text
codex/feat/iemp-42-telemetry-ingestion
codex/fix/iemp-57-reconnect-backoff
codex/docs/iemp-63-local-setup
```

For initial scaffolding only, `codex/chore/repository-bootstrap` is allowed.

## Commit convention

Use Conventional Commits with an imperative summary and the issue ID:

```text
<type>(<scope>): <summary> [IEMP-<issue-number>]
```

Use a task ID instead when the commit maps to a specific checklist task:

```text
feat(gateway): buffer offline telemetry [IEMP-42-T2]
fix(firmware): retry failed sensor reads [IEMP-57]
docs(repo): document local setup [IEMP-63]
```

| Type | Use |
| --- | --- |
| `feat` | New behavior or capability. |
| `fix` | Correct a defect. |
| `docs` | Documentation changes. |
| `refactor` | Restructure code without changing behavior. |
| `test` | Add or update tests. |
| `perf` | Improve performance. |
| `build` | Toolchains, dependencies, or build configuration. |
| `ci` | Continuous integration configuration. |
| `chore` | Repository maintenance. |
| `revert` | Revert a previous change. |

Scopes are `firmware`, `gateway`, `backend`, `frontend`, `simulator`, `infra`,
`docs`, `tests`, or `repo` for shared changes. Use `!` before the colon for a
breaking change and explain the impact and migration in a `BREAKING CHANGE:`
footer.

The bootstrap commit may use `chore(repo): scaffold workstreams and conventions`.

## Pull requests and validation

1. Reference the issue and describe the behavior or documentation being changed.
2. State how the acceptance criteria were checked, including commands and results
   when applicable. If checks are not available yet, say so.
3. Update affected setup instructions, contracts, and configuration examples.
4. Use `Closes #42` only when the pull request fully completes the issue; use
   `Refs #42` for partial work.
5. Prefer squash merging and use the commit convention for the resulting commit.

## Shared repository rules

- Follow `.editorconfig`; add workstream-specific formatters when their
  toolchains are selected.
- Keep generated output, local environment files, and secrets out of Git. Commit
  sanitized examples and dependency lockfiles for reproducible setup.
- Put unit tests within their workstream and shared integration tests in `tests/`.
- Document shared contracts and architecture decisions in `docs/`.
- Add executable setup and validation instructions with each new workstream's
  first implementation.
