# Backlog-by-file cycle 4 — Requirements + Acceptance Criteria

**Date:** 2026-04-17
**Branch:** `feat/backlog-by-file-cycle4`
**Prior cycles:** cycle 1 PR #13 (38 items / 18 files), cycle 2 PR #14 (30 / 19), cycle 3 PR #15 (24 / 16)

## Problem

`BACKLOG.md` contains ~90 open items in Phase 4.5 post-v0.10.0 audit (30+ HIGH, 40+ MEDIUM, 20+ LOW). Cycles 1–3 closed 92 items via file-grouped batches. Cycle 4 continues that cadence, focusing on mechanical fixes whose recipes are pre-specified in the BACKLOG entry. Per user feedback memory `feedback_batch_by_file`: group by file (HIGH + MED + LOW together), target 30–40 items across 15–20 files.

## Non-goals

- Architectural rewrites (state-store fan-out, manifest claim-then-commit, `compile_wiki` two-phase pipeline, `config.py` split, `kb/__init__.py` curated re-exports).
- Vector-index lifecycle cycle (atomic temp-DB rebuild, cold-load latency, dim-mismatch, `_index_cache` cross-thread symmetry) — explicitly deferred per cycle 1 HIGH spec.
- Multiprocessing `file_lock` tests — explicitly deferred to a dedicated test-infrastructure cycle.
- CLI ↔ MCP parity auto-generation — requires FastMCP registry introspection design.
- Phase 5 feature proposals (Tier 1/2/3).
- Any item requiring a new dependency.

## Candidate items (30 items, 16 files)

Each line: BACKLOG severity + symbol-level hint + one-line fix description.

### `src/kb/mcp/core.py` (5)
1. R1: `_rel()` every error-string interpolation (strip absolute path leakage) — affects ~5 raise sites.
2. R1: `kb_query.conversation_context` — strip control chars + wrap in `<prior_turn>` sentinel before passing to rewriter LLM.
3. R4: citation format guidance → `[[page_id]]` wikilinks (replace `[source: page_id]`).
4. R4: `kb_ingest` `source_type` validated against `SOURCE_TYPE_DIRS` keys after empty-string branch.
5. R4: `kb_ingest_content` / `kb_save_source` OSError after successful create → return `Error[partial]: …` with `overwrite=true` hint.

### `src/kb/mcp/browse.py` (3)
6. R4: `kb_search` enforce `MAX_QUESTION_LEN` + surface `[STALE]` marker in formatted output.
7. R4: `kb_read_page` cap body at `QUERY_CONTEXT_MAX_CHARS` with `[Truncated: …]` footer.
8. R4: `kb_read_page` ambiguous case-insensitive match → `Error: ambiguous page_id` (no first-wins).

### `src/kb/mcp/quality.py` (4)
9. R4: `kb_create_page` title length cap (≤500) + strip control chars.
10. R3: `kb_create_page` `source_refs` must exist on disk (`(PROJECT_ROOT / src).is_file()`).
11. R4: `kb_affected_pages` `_validate_page_id(..., check_exists=True)`.
12. R1: `kb_save_lint_verdict` per-issue `description` ≤ 4KB cap at library boundary (`add_verdict`).

### `src/kb/mcp/app.py` (1)
13. R4: `_validate_page_id` reject Windows reserved names (`CON`/`PRN`/`AUX`/`NUL`/`COM1-9`/`LPT1-9`) + enforce `len(page_id) ≤ 200`.

### `src/kb/mcp/health.py` (1)
14. R4: `kb_detect_drift` surface deleted raw sources as third category (`source-deleted`) in affected pages list.

### `src/kb/query/rewriter.py` (1)
15. R4: `_should_rewrite` skip canonical WH-questions (`who|what|where|when|why|how … ?` with proper-noun token) AND handle CJK scripts (whitespace tokenization fails → use `len(question.strip()) < 15` universal short-query signal).

### `src/kb/query/engine.py` (1)
16. R2: `search_pages` BM25 module-level cache keyed on `(wiki_dir, max_mtime)`.

### `src/kb/query/dedup.py` (1)
17. R2: `_enforce_type_diversity` — recompute `max_per_type` against running quota (post-dedup) or use running-quota pattern.

### `src/kb/utils/text.py` (2)
18. R4: drop `"new"`/`"all"`/`"more"`/`"other"`/`"some"`/`"only"`/`"most"`/`"very"` from `STOPWORDS` (technical entity names).
19. R4: `yaml_escape` strip leading BOM (`\ufeff`), reject U+2028 / U+2029 line separators, document double-quoted-scalar-only contract.

### `src/kb/utils/wiki_log.py` (1)
20. R4: rotate to `wiki/log.YYYY-MM.md` at `LOG_SIZE_WARNING_BYTES` threshold (currently only warns).

### `src/kb/lint/checks.py` (1)
21. R4: `check_source_coverage` — short-circuit on missing frontmatter fence with `logger.warning` + surface as `malformed_frontmatter` issue (distinct from "source not referenced").

### `src/kb/ingest/contradiction.py` (1)
22. R5: `detect_contradictions` return dict `{contradictions, claims_checked, claims_total, truncated}` so `ingest_source` / MCP callers can surface truncation telemetry; promote truncation log to `WARNING`.

### `src/kb/graph/export.py` (1)
23. R1: `export_mermaid(graph: Path | DiGraph)` isinstance shim → add `DeprecationWarning` with removal target in next release.

### `src/kb/query/bm25.py` (1)
24. R1: `BM25Index` precompute postings list in `__init__`; `score()` skips docs not containing any query term (sparse-query speedup).

### `src/kb/compile/compiler.py` (1)
25. R4: `_template_hashes` — whitelist YAML filenames against `VALID_SOURCE_TYPES` to reject editor backup files (`*.bak`, `*.swp`).

### `.env.example` (1)
26. R3: add commented `CLAUDE_SCAN_MODEL` / `CLAUDE_WRITE_MODEL` / `CLAUDE_ORCHESTRATE_MODEL` vars to `.env.example` to close drift vs `config.py:65-69`.

### `CLAUDE.md` (1)
27. R3: `query_wiki` signature section — add `conversation_context` param + `stale` return-dict key to docs.

### `src/kb/utils/pages.py` (1)
28. R4: `load_purpose()` — require `wiki_dir` arg explicitly; remove silent production-wiki fallback.

### `src/kb/compile/linker.py` (1)
29. R4: `inject_wikilinks` — sort titles descending by `len()` before substitution to prevent overlapping title collision (e.g. `RAG` vs `Retrieval-Augmented Generation`).

### `src/kb/review/refiner.py` (1)
30. R4: import and reuse `FRONTMATTER_RE` from `utils/markdown.py` in `refine_page` — removes leading-whitespace permissiveness divergence.

## Acceptance criteria

- **AC1 — Regression safety:** `python -m pytest` green; no existing test's expectations changed unless BACKLOG item explicitly corrects behaviour.
- **AC2 — Behavioural coverage:** each fix has at least one regression test exercising the production code path (not signature-only — per `feedback_test_behavior_over_signature`). Target ≥28/30 items backed by new/amended tests.
- **AC3 — Lint clean:** `ruff check src/ tests/` + `ruff format --check src/ tests/` both pass.
- **AC4 — Doc sync:** `CHANGELOG.md [Unreleased]` entry lists every fixed item with BACKLOG reference; `BACKLOG.md` **deletes** each resolved item (never strikethrough) per user memory; `CLAUDE.md` test count + tool count updated if changed.
- **AC5 — No PR-introduced CVEs:** Step 11 pip-audit diff vs Step 2 baseline is empty.
- **AC6 — File-grouped commits:** one commit per file (or tight file-cluster), matching cycles 1–3 pattern for reviewability.

## Blast radius

- **Tool boundary:** `src/kb/mcp/` (5 files) — all changes backward-compatible (tightening validation, adding optional args).
- **Search / query:** `src/kb/query/` (4 files) — changes are additive (caches, skip-heuristics, telemetry); query answers semantically unchanged.
- **Utilities:** `src/kb/utils/` (3 files) — `STOPWORDS` change affects BM25 ranking on queries with now-unstopped words (test coverage required).
- **Ingest / compile / lint:** 1 file each — all local, no API-surface churn.
- **Docs:** `CHANGELOG.md`, `BACKLOG.md`, `CLAUDE.md`, `.env.example` — content only.

## Verification checkpoint (from cycle 3 R1 lesson)

Before Step 5 decision gate approves the design, `grep -n "<symbol>" src/` must be run for every candidate item. Any symbol whose fix was already shipped in cycles 1–3 gets dropped from scope with a DROPPED-ALREADY-SHIPPED note in the decision doc. Current BACKLOG.md comments mark cycle-1 / cycle-2 / cycle-3 closures inline; design eval must reconcile against them.

## Out-of-scope deferrals (documented for future cycles)

- Vector-index lifecycle rewrite → standalone cycle.
- Manifest claim-then-commit → requires `file_lock` cross-process test harness first.
- `cli.py` function-local imports → requires smoke-test harness first.
- `compile_wiki` two-phase pipeline → architectural; design spec needed.
- `config.py` split → architectural; `from kb.config import *` shim required.
- `kb/__init__.py` + `models/__init__.py` + `utils/__init__.py` curated re-exports → one cycle, all packages together.
