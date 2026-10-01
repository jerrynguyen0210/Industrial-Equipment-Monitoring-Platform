# Contributing

## 1. Create or select an issue

GitHub Issues are the source of truth. The issue number becomes the work ID:
`IEMP-<number>`; issue `#42` is `IEMP-42`.

For checklist work, append `-T<number>` without renumbering existing tasks:

```markdown
- [ ] IEMP-42-T1: Define the telemetry payload.
- [ ] IEMP-42-T2: Implement forwarding.
```

Create a linked issue when a task needs its own tracking. The initial repository
bootstrap is the only work that may omit an issue ID.

## 2. Create a branch

Use a short-lived branch based on `main`:

```text
codex/<type>/iemp-<issue>-<description>
```

Example: `codex/feat/iemp-42-telemetry-ingestion`. Use lowercase words separated
by hyphens and keep one issue per branch.

## 3. Commit the change

Use an imperative Conventional Commit subject:

```text
<type>(<scope>): <summary> [IEMP-42]
```

Example: `fix(firmware): retry failed sensor reads [IEMP-57]`.

Types are `feat`, `fix`, `docs`, `refactor`, `test`, `perf`, `build`, `ci`,
`chore`, and `revert`. Scopes are `firmware`, `gateway`, `backend`, `frontend`,
`simulator`, `infra`, `docs`, `tests`, or `repo`. Mark a breaking change with
`!` and a `BREAKING CHANGE:` footer.

## 4. Validate and open a pull request

1. Run the affected component checks.
2. Update related setup, configuration, and contract documents.
3. Reference the issue and list the commands and results used for validation.
4. Use `Closes #42` only when the pull request completes the issue; otherwise
   use `Refs #42`.
5. Prefer squash merging and format the final commit with the convention above.

## Repository rules

- Follow `.editorconfig` and the component coding conventions.
- Never commit secrets, local environment files, generated output, or build files.
- Commit sanitized examples and dependency lockfiles.
- Keep unit tests beside their component; put cross-component tests in `tests/`.
- Record shared contracts and architecture decisions in `docs/`.
- Include runnable setup and validation instructions with new components.
