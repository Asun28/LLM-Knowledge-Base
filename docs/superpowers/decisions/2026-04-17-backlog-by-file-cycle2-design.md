# Backlog-by-file cycle 2 — design decision doc (Step 5 gate)

**Date:** 2026-04-17
**Spec:** `docs/superpowers/specs/2026-04-17-backlog-by-file-cycle2-design.md`
**Gate:** Opus subagent (auto-approve)
**Outcome:** APPROVE-WITH-CONDITIONS → 12 amendments → APPROVED for Step 7.

## Decisions (Q-by-Q)

| Q | Topic | Decision | Confidence |
|---|---|---|---|
| Q1 | `file_lock` ASCII decode failure | RAISE (not WARN+steal). Startup `_purge_legacy_locks()` handles migration. | High |
| Q2 | `LLMError` truncation cap | `e.message` only, ≤500 chars via `cli._truncate`. Preserve verbatim: exception class, `model`, `status_code`, `retry_attempt`. | High |
| Q3 | `hybrid_search` log proxy | `len(question.split())` (whitespace-split, cheap). | High |
| Q4 | Evidence pipe escape location | RENDER TIME (`format_evidence_entry`). Stored entry stays byte-clean. | High |
| Q5 | 2MB cap mode | `st_size` pre-check (fail fast). Config constant `RAW_SOURCE_MAX_BYTES = 2_097_152` in `kb.config`. | High |
| Q6 | Item 2 vs Risk-register conflict | RAISE wins. Delete legacy UTF-8 tolerance bullet; replace with startup-purge. | High |
| Q7 | Rescue refiner two-phase write | DEFERRED. Audit-trail ordering deserves own design note. | High |
| Q8 | `\s+` collapse cache invalidation | None needed — BM25 path only; add assertion test. | Medium |
| Q9 | `wiki_log.py` LF-only open | INCLUDE as item 29 (rides with item 8-9 commit). | High |
| Q10 | `dedup_results` content_lower fallback | INCLUDE as item 30 (rides with item 15 commit). | High |
| Q11 | `LLMError` BadRequestError redaction | DEFER. Requires redaction-surface design; new BACKLOG entry referencing BACKLOG:701. | High |

## Conditions applied to spec

1. Scope bumped 28 → 30 items, 19 files unchanged.
2. Item 2 rewritten: RAISE on unparseable lock file + `_purge_legacy_locks()` at module load.
3. Risk-register UTF-8 tolerance bullet deleted; purge bullet added.
4. Item 7 amendment: `cli._truncate` DRY; four preserved fields; `__repr__` test.
5. Item 13 amendment: `RAW_SOURCE_MAX_BYTES` config constant; `st_size` pre-check; skip-log format.
6. Item 16 amendment: structured WARN log with backend + exception class + token proxy.
7. Item 28 amendment: move to `format_evidence_entry`; stored entry unchanged.
8. New item 29 (`utils/wiki_log.py` LF newline).
9. New item 30 (`query/dedup.py` content_lower fallback).
10. Item 12 amendment: rewriter identical-cache assertion for `\s+` collapse.
11. Deleted spec's own "Open questions for Step 5 gate" section.
12. Commit count unchanged (19); items 29/30 absorbed into existing commits.

## Follow-up BACKLOG entries to add

- `utils/llm.py` — redact `BadRequestError.e.message` for non-retryable errors to prevent prompt/body leakage (LOW, references BACKLOG:701). Owner: next cycle.
- `review/refiner.py` — two-phase write-then-audit (HIGH, deferred from cycle 1). Owner: dedicated cycle.
- Vector-index lifecycle cycle — atomic rebuild, cold-load, dim-mismatch validation, `_index_cache` lock symmetry. Owner: dedicated cycle.

## No escalation

Every Q resolved against a project principle (lower blast radius, reversible, opt-in, trace-to-request) or threat-model bias. Proceed to Step 7.
