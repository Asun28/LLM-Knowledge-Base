# Cycle 62 Requirements

## Goal
Continue the Phase 4.5 HIGH `tests/` coverage-visibility backlog fix by
folding 20 remaining versioned/cycle-specific test files into canonical receiver
test files.

## Acceptance Criteria
- AC1: Fold exactly 20 selected source test files into existing canonical
  receiver files.
- AC2: Preserve all 97 selected source tests with no behavior changes.
- AC3: Delete the 20 obsolete source files after their tests land in receivers.
- AC4: Keep runtime code, dependency manifests, CI workflows, and public APIs
  untouched.
- AC5: Verify selected source baseline, targeted receiver tests, ruff, full
  pytest, docs validation, and diff hygiene.
- AC6: Update `BACKLOG.md`, `CHANGELOG.md`, `CHANGELOG-history.md`,
  `CLAUDE.md`, `docs/reference/testing.md`,
  `docs/reference/implementation-status.md`, and any user-facing count mirrors.

## Baseline
- Test files: `200`.
- Pytest collection: `3022 tests collected`.
- Selected source tests: `97 passed`.

## Out Of Scope
- Production backlog fixes.
- New dependencies.
- CI workflow changes.
- A new query-format receiver file.
