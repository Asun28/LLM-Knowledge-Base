# Cycle 20 — Brainstorming

**Date:** 2026-04-21
**Inputs:** `2026-04-21-cycle20-requirements.md` (21 ACs, 7 clusters) + `2026-04-21-cycle20-threat-model.md` (T1–T7).

For each cluster, enumerate 2–3 realistic approaches + pick a tentative winner + call out the open question that must resolve at Step 5.

---

## Cluster A — `kb.errors` exception taxonomy

### Approach A1 — Flat `src/kb/errors.py` single file (~60 LOC)
All five subclasses + `KBError` base in one module. Cheap to read, cheap to import, easy to audit. Re-exported from `kb/__init__.py`. Matches convention of `kb.errors` in most mid-sized Python projects.

### Approach A2 — Package `src/kb/errors/` with `base.py` + per-kind files
More ceremony; useful only if each kind accumulates >10 subclasses or attaches helper functions. At cycle-20 scope (6 classes) this is over-engineered.

### Approach A3 — Reuse `kb.utils.llm.LLMError` as base (rename to `KBError`)
Backwards-compat trick: keep `LLMError` identifier pointing at a renamed subclass. Saves one file but conflates "network/LLM failure taxonomy with `.kind`" and "general KB base class". Rejected — concept drift.

**Pick:** A1. 50-60 LOC flat module. No package.

**Open Q1:** AC5 narrow-migration is 3 sites (compile outer, ingest outer, query outer). Should we also rewrap the `LLMError` raises at `kb/utils/llm.py:377,378` to pass through `kb.errors.QueryError` when already inside a query context? No — `LLMError` IS the taxonomy for LLM failures; query/ingest callers catch `LLMError` as a sibling. Keep separate.

**Open Q2:** Should `StorageError` carry a `path: Path | None` instance attribute (T1 mitigation) even when `kind` is None? Yes — callers can introspect `.path` when handling, but `__str__` only renders if `kind` is set. Default `None` means no leak.

---

## Cluster B — `_write_wiki_page` O_EXCL hardening

### Approach B1 — Add `exclusive=True` kwarg that switches the write to `os.open(O_EXCL)` when set
Minimal API change. Callers opt in. Low blast radius. Matches `kb_create_page`/`capture` existing pattern. On conflict, raise `StorageError(kind="summary_collision")`.

### Approach B2 — Always O_EXCL; delete the `atomic_text_write` path
Breaks every existing `_write_wiki_page(path=…)` call that expects overwrite semantics (used at AC9 legacy callers + `_update_existing_page` helpers?). Requires caller audit. Rejected — too wide for cycle 20.

### Approach B3 — Caller-side `path_lock` around `exists() + write` instead of O_EXCL
`file_lock(path)` is per-page cross-process. Closes the same TOCTOU but without the atomicity guarantee of O_EXCL (any third process writing without the lock still races). O_EXCL is strictly safer; lock is complementary. Ship BOTH (AC11 mitigation for T3 also wraps the create+evidence_trail in `file_lock(page_path)`).

**Pick:** B1 + B3 together. `exclusive=True` on `_write_wiki_page` + `file_lock(page_path)` around the create+evidence-trail span at caller. Belt-and-braces — O_EXCL owns the atomic-reserve guarantee, `file_lock` owns the cross-process serialization of the evidence-trail append.

**Open Q3:** On Windows, POSIX `O_NOFOLLOW` doesn't exist. Mitigation T3 says guard with `hasattr(os, "O_NOFOLLOW")`. Verified stdlib behaviour — is Windows `CreateFileW(CREATE_NEW)` alone sufficient against symlink-target swap? Yes — on Windows reparse points can only be traversed with `FILE_FLAG_OPEN_REPARSE_POINT`, which `os.open` does not set; default behaviour follows the reparse point but `CREATE_NEW` refuses to create if the target exists, so the symlink-swap variant lands as FileExistsError. Approved.

**Open Q4:** Concurrent-write test uses `threading.Thread × 2` or `multiprocessing.Process × 2`? Thread is simpler + cycle-17 L1 explicitly marks multiprocess lock tests as deferred. Thread catches the intra-process TOCTOU; cross-process is documented in BACKLOG for a dedicated cycle. Approved: threading.

---

## Cluster C — `sweep_stale_pending` mutation tool

### Approach C1 — Single function with `action: Literal["mark_failed", "delete"]`
Combined surface, one entry point, easy to test. Default is safe (`mark_failed` preserves data).

### Approach C2 — Two separate functions (`mark_stale_pending_failed`, `delete_stale_pending`)
More explicit API. Harder to misuse via MCP (no magic-string action). More boilerplate for CLI/MCP shims. Same net code size.

### Approach C3 — Single-function with explicit `--yes` confirmation for `delete`
MCP/CLI require `confirm_delete=True` keyword when action is `delete`. Adds safety at cost of API complexity.

**Pick:** C1 + audit trail (T4 mitigation). `action` enforced to `{"mark_failed", "delete"}`. `delete` path writes a `wiki/log.md` line BEFORE the mutation (so crash mid-sweep leaves the audit trail). `mark_failed` default keeps the row content preserved.

**Open Q5:** Default `hours=168` (1 week) — matches `list_stale_pending` default of `24`? Different defaults are OK because the use cases differ: `list_stale_pending` surfaces "pending for >24h for operator attention"; `sweep_stale_pending` at `168h` is "definitely abandoned, safe to mark failed". Operators can override.

**Open Q6:** Does `delete` need a dry-run mode? Add `dry_run: bool = False` kwarg — when True, return the rows that WOULD be affected without mutating. Cheap to add, high operator value. APPROVE dry_run addition to AC13/14/15.

**Open Q7:** `sweep_id` uniqueness across runs — uuid4 hex[:8] gives ~4B unique values. Probabilistic collision with prior sweeps over years is fine. Approve.

---

## Cluster D — `list_stale_pending` MCP/CLI surface

### Approach D1 — MCP returns same fields as library helper
`[{attempt_id, timestamp, page_id, revision_notes, status, ...}]` verbatim. Leaks `revision_notes` per T5.

### Approach D2 — MCP projects minimal field set (T5 mitigation)
`[{attempt_id, timestamp, page_id, content_length}]`. CLI gets the full structure for local-only use.

### Approach D3 — MCP adds explicit `include_notes=False` toggle
Opt-in expansion. Future-proof. Over-engineered for cycle 20.

**Pick:** D2. MCP projection matches existing MCP privacy discipline (redacting paths, redacting raw content). CLI keeps the full dict since it runs locally.

**Open Q8:** `content_length` field — does it exist in the pending row? `refine_page` records `{attempt_id, timestamp, page_id, status, revision_notes, content_hash}`. `len(revision_notes)` is a decent proxy; add `notes_length` explicitly. APPROVE — AC17 projects `{attempt_id, timestamp, page_id, notes_length: len(row.get("revision_notes", ""))}`.

---

## Cluster E — Windows tilde-path test

### Approach E1 — ctypes + `GetShortPathNameW`
Direct Win32 API. Correct. Requires ctypes setup + platform-specific skip.

### Approach E2 — `subprocess.run(["cmd", "/c", "for %I in (...) do @echo %~sI"])`
Batch-shell approach. More brittle (shell quoting) but no ctypes.

### Approach E3 — Use `os.path.realpath` + construct tilde manually from parent chain
Brittle heuristic; tilde suffix depends on filesystem state (how many siblings exist with the same first-6-char prefix). Rejected.

**Pick:** E1 ctypes `GetShortPathNameW` with 260-char buffer (T6 mitigation) + platform skip + runtime skip when short==long.

**Open Q9:** Does the test need to roundtrip `GetLongPathNameW(short_path)` == `long_path` to confirm the fixture is real? Belt-and-braces but out of scope. AC20 tests the production invariant only (tilde and long form yield same manifest key). APPROVE.

---

## Cluster F — diskcache CVE check

### Approach F1 — `pip index versions diskcache` + compare to pinned
Simple. Returns list of available versions. Compare against the pinned `5.6.3` and the CVE `first_patched_version`. If a newer patched version exists, bump.

### Approach F2 — `pip-audit` parse + auto-propose bump
Already captures the finding in baseline. Easier to report than to decide.

### Approach F3 — GHSA API lookup for current advisory state
Expensive, needs token. Rejected.

**Pick:** F1 + report. Non-code deliverable: dated re-check note in BACKLOG + CHANGELOG if still unpatched; bump + remove-backlog if patched. Step 11.5 either runs (bump commit) or skips (documented).

---

## Cross-cluster open questions

**Open Q10:** Should we add `tests/test_cycle20_errors_taxonomy.py` assertions that NO module imports `from kb.errors import *`? The star-import would defeat the narrow-import discipline. ACCEPT as a minor lint check; add one grep-based test.

**Open Q11:** Does the primary session own Step 7 plan per cycle-14 L1 (≥15 ACs + full Steps 1-5 context)? YES — cycle 20 has 21 ACs and I drafted Steps 1+2+3 directly. Stay on primary.

**Open Q12:** Should we gate on `ruff format --check` clean BEFORE Step 10 so any formatting lands in the impl commits? YES — cycle 19 L2 loosely suggested formatting should happen inline with Edits. Run ruff format after each cluster lands, not at the end.

**Open Q13:** Codex dispatch budget for Step 9 — the 21 ACs span 5 test files + 9 prod files. Per cycle-13 L2, tasks <30 LOC+<100 test LOC should stay in primary. Cluster A's migration is tiny (3 site narrow); Cluster B's `_write_wiki_page` patch is ~30 LOC + ~80 test LOC; Clusters C/D are ~120 LOC helper + MCP wrappers. Hybrid: A+B in primary; C+D+E dispatched to Codex (independent) run_in_background; F handled inline.

**Open Q14:** Should AC9's summary write pivoting to `_update_existing_page` be guarded by `StorageError.kind == "summary_collision"`? YES — the `.kind` field is the branching contract; string-match on the error message is fragile. Use `isinstance(err, StorageError) and err.kind == "summary_collision"`.

**Open Q15:** For MCP `kb_refine_sweep`, who audits the action? Per T4 mitigation — for `action="delete"`, the sweep writes a `wiki/log.md` entry BEFORE mutating `review_history.json`. For `action="mark_failed"`, the row itself carries `sweep_id` + `sweep_at` — no log entry needed (the row preserves the audit trail).

---

## Decisions parked for Step 5

Q1 (kb.utils.llm passthrough) → RESOLVED: keep LLMError separate, no passthrough.
Q2 (StorageError.path attr) → PROPOSE: add path attr; hide from __str__ unless kind is set.
Q3 (Windows O_EXCL symlink semantics) → PROPOSE: guard O_NOFOLLOW with hasattr; rely on CreateFileW for Windows.
Q4 (thread vs multiprocess test) → RESOLVED: threading (intra-process).
Q5 (default hours) → RESOLVED: list=24, sweep=168.
Q6 (dry_run) → PROPOSE: add dry_run kwarg to AC13/14/15.
Q7 (sweep_id uniqueness) → RESOLVED: uuid4.hex[:8] good enough.
Q8 (notes_length projection) → RESOLVED: MCP returns notes_length, not revision_notes.
Q9 (long-path roundtrip assertion) → RESOLVED: skip, AC20 tests production invariant only.
Q10 (star-import lint) → PROPOSE: add one grep-based test.
Q11 (primary session Step 7) → RESOLVED.
Q12 (ruff format inline) → RESOLVED.
Q13 (Codex dispatch budget) → RESOLVED: hybrid.
Q14 (StorageError branching contract) → RESOLVED: kind-based, not string.
Q15 (sweep audit trail) → RESOLVED: log.md before delete, sweep_id in row for mark_failed.
