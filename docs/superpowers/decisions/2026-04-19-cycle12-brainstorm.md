# Cycle 12 — Brainstorm (Step 3)

Scope is deterministic (17 ACs fully enumerated in requirements + threat-model docs). Brainstorm focuses on commit shape, dependency ordering, and rollback granularity.

## Approach A — one commit per AC (17 commits)

- Pros: bisect-friendly; every AC is independently reviewable; a PR-review blocker rollback loses exactly one AC.
- Cons: 17 Codex dispatches serially — noisy PR log; some single-line doc-only commits feel wasteful.
- Risk: AC8 (helper) + AC9 (single-site migration) in the same file but in different commits means a future reader may rediscover the helper-then-migrate story from git log. Not a blocker.

## Approach B — cluster-by-logical-unit (~8 commits)

- Commit 1: helper `load_page_frontmatter` + single-file migration (AC8 + AC9 clustered — same file, atomic contract).
- Commit 2: cross-file migrations to the new helper (AC11, graph/export.py, review/context.py, lint/semantic.py, lint/augment.py — but requirements only scope AC11 for lint/checks.py; do not expand here).
- Commit 3: `KB_PROJECT_ROOT` + walk-up (AC5 + AC6 — same file and logically one feature).
- Commit 4: `sweep_orphan_tmp` helper (AC2) + `utils/io.py` docstrings (AC3 + AC4).
- Commit 5: `tmp_kb_env` fixture (AC1) + its regression test.
- Commit 6: MCP console-script collapse (AC7 — crosses 3 files but one feature).
- Commit 7: `graph/builder.py` doc (AC10).
- Commit 8: cycle-12 regression tests (AC12, AC13, AC14, plus the tests pinning AC1/AC2/AC5/AC7/AC8).
- Commit 9: BACKLOG sweep + CHANGELOG + CLAUDE.md (AC15 + AC16 + AC17).
- Pros: fewer commits; natural atomic units; helper+migration always together.
- Cons: multi-file commits (AC7) slightly violate strict per-file convention — acceptable as a "cluster" per cycle-4 plan-gate amendment.

## Approach C — strict one-commit-per-file (13 commits)

- Pros: matches `feedback_batch_by_file` literally.
- Cons: AC7 splits across `mcp/__init__.py`, `mcp_server.py`, and `pyproject.toml` — three commits for one atomic console-script rewire means the middle commit ships a broken state (not quite, but close). Same for AC5+AC6 potentially.

## Decision

**Adopt Approach B (cluster by logical unit, ~8-9 commits).** Matches cycle 11's shape (14 AC → 13 implementation commits, with one AC4+AC5 cluster). The per-file discipline is a guideline, not an absolute; cycle-4's plan-gate amendment explicitly allows "cluster commits" when a helper + caller must ship together for atomicity. Each commit is still reviewable in isolation.

## Ordering (dependency-respecting)

1. `tests/conftest.py` → `tmp_kb_env` fixture MUST ship before any cycle-12 regression test uses it.
2. `src/kb/utils/io.py` → `sweep_orphan_tmp` helper + docstrings; independent.
3. `src/kb/config.py` → `KB_PROJECT_ROOT` + walk-up; independent.
4. `src/kb/utils/pages.py` → `load_page_frontmatter` helper + local migration (AC8 + AC9).
5. `src/kb/graph/builder.py` → docstring (AC10); independent.
6. `src/kb/lint/checks.py` → 4-site migration to helper (AC11); depends on step 4.
7. `src/kb/mcp/__init__.py` + `src/kb/mcp_server.py` + `pyproject.toml` → AC7 cluster; independent.
8. Regression tests for AC14 (`conversation_context`), AC12 (`kb lint --augment --execute --wiki-dir`), AC13 (`run_augment` default-path), plus pinning tests for AC1 (fixture usage), AC2 (sweep), AC5/6 (env+walkup), AC7 (console script), AC8/9/11 (cache hit rate); some of these ship alongside their corresponding production commits.
9. `BACKLOG.md` stale sweep + `CHANGELOG.md` + `CLAUDE.md` refresh.

## Open questions (for Step 5 Opus gate)

- **Q1 — Scope of AC11 frontmatter migration:** Requirements list ONLY lint/checks.py (4 sites); should we extend to `lint/augment.py` (5 sites) + `lint/semantic.py` (1 site) + `graph/export.py` (1 site) + `review/context.py` (1 site) in the same cycle? Arguments for: same MEDIUM R1 item, closes the class. Arguments against: more blast radius, more callers to regression-test, violates Step-1 scope boundary.
- **Q2 — AC7 shim strategy:** `src/kb/mcp_server.py` re-exports `main` but keeps `if __name__ == "__main__": main()`; do we also keep the module-level `mcp` re-export for callers doing `from kb.mcp_server import mcp`? (Cycle-8 AC30 --version short-circuit relies on NOT loading mcp_server when running cli; this must remain intact.)
- **Q3 — AC1 `tmp_kb_env` and `_reset_embeddings_state`:** The existing autouse `_reset_embeddings_state` fixture in conftest yields between setup and teardown. New fixture must not interfere with this ordering. Should `tmp_kb_env` be request-scoped (opt-in) or session-scoped (autouse)? Threat model note (4) explicitly says NOT autouse.
- **Q4 — AC14 regression scope:** Should the conversation_context pin also verify the `use_api=True` rewriter path (not just the default stdout-only path)? The cycle-4 fix was specifically for the rewriter LLM input, so YES — cover both paths.
- **Q5 — Stale-BACKLOG aggressiveness:** AC15 lists one stale item (conversation_context). Should we audit the rest of the Phase 4.5 LOW/MEDIUM sections for other stale entries as part of this cycle? Arguments for: "backlog cleaned" is in user's request. Arguments against: risk of deleting open items by mistake; each deletion requires grep-verify against source.

These questions feed Step 4 design eval and Step 5 decision gate.
