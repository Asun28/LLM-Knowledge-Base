# Backlog-by-file cycle 2 — design spec

**Date:** 2026-04-17
**Pipeline:** feature-dev cycle (16 steps)
**Precedent:** cycle 1 (PR #13, merged 2026-04-17, 38 items / 18 files / 3 review rounds)

## Problem

After cycle 1, Phase 4.5 HIGH/MEDIUM/LOW sections still contain ~140 open mechanical items, plus
Phase 5 pre-merge reviews add another ~30. User asked to close "as many as" possible in one
batch-by-file cycle, follow the feature-dev skill end-to-end, verify all tests, and keep docs
in sync. Auto-approve discipline applies — all gate approvals go to Opus sub-agents.

## Non-goals (explicit deferrals)

These items require dedicated cycles because they change a public contract, invert a module
dependency, or span >1 architectural layer:

| Item | Reason deferred |
|---|---|
| `kb/__init__.py` + `models/__init__.py` + `utils/__init__.py` public re-exports | Breaking-change review; needs downstream-caller audit. |
| `compile/` ↔ `ingest/` directory naming inversion | Directory restructure; every import path changes. |
| MCP 25-tool sync→async migration | Concurrency contract; FastMCP thread-pool interaction. |
| `config.py` god-module split into `config/paths.py`, `config/search.py`, … | Import-graph risk; needs migration shim. |
| `ingest_source` 11-stage state-store fan-out + per-page lock discipline | Multi-stage architectural; needs receipt/replay design. |
| Two-pass `_write_item_files` for `raw/captures/` alongside-staleness (Phase 5 pre-merge R3 CRITICAL) | Needs a dedicated design spec (noted `# TODO(v2)` in capture.py). |
| Phase 5 features (`kb_merge`, `belief_state`, inline claim tags, `/llms.txt`) | Feature work, not bug fix. |
| Vector-index lifecycle cycle (atomic rebuild + cold-load + dim-mismatch validation) | Called out in BACKLOG as "bundle into dedicated cycle". |
| `review/refiner.py` two-phase write-then-audit ordering | Called out in BACKLOG as "deferred from cycle 1 HIGH". |

## In-scope items (~28, across ~19 files)

Grouped by file. Every item has an existing BACKLOG entry unless noted `NEW`.

### utils/ — 11 items, 7 files

| # | File | Item | Severity |
|---|---|---|---|
| 1 | `utils/io.py` | `file_lock` — set `acquired=True` AFTER `os.write` returns successfully; reword comment | LOW (R6) |
| 2 | `utils/io.py` | `file_lock` — `read_text(encoding="ascii")`; on decode/`int()` failure, RAISE don't steal. Add `_purge_legacy_locks()` at module load (one-time migration, deletes any non-ASCII-int lock file in `.data/locks/`; idempotent; logs INFO with count) | MED (R3) |
| 3 | `utils/io.py` | `atomic_json_write` / `atomic_text_write` — `f.flush() + os.fsync()` before `replace` | MED (R5) |
| 4 | `utils/io.py` | `atomic_json_write` / `atomic_text_write` — log WARNING on cleanup `unlink` failure | MED (R5) |
| 5 | `utils/llm.py` | `call_llm_json` — collect ALL `tool_use` blocks; on no match, include leading text in `LLMError` | HIGH (R4) |
| 6 | `utils/llm.py` | `_backoff_delay` — add `random.uniform(0.5, 1.5)` jitter, clamp to `RETRY_MAX_DELAY` | MED (R5) |
| 7 | `utils/llm.py` | `LLMError` wrap — truncate `e.message` to ≤500 chars via `cli._truncate` (DRY); preserve verbatim: exception class name, `model`, `status_code`, `retry_attempt` | MED (R4) |
| 8 | `utils/wiki_log.py` | Escape leading `#`/`-`/`>`/`!` and `[[`/`]]` in operation and message before write | MED (R4) |
| 9 | `utils/wiki_log.py` | After `FileExistsError pass`, re-run `_reject_if_not_regular_file` before `open("a")` | MED (R5) |
| 10 | `utils/markdown.py` | `extract_frontmatter_body` — fast-path `content.startswith("---")` before running regex | MED (R2) |
| 11 | `utils/hashing.py` | `content_hash` — CRLF / CR → LF normalize before hashing | LOW (R1) |

_(Originally listed `utils/text.py` BOM strip + `utils/pages.py` explicit `wiki_dir`; both dropped from scope after Step 5 gate review — see decision doc.)_

### query/ — 6 items, 5 files

| # | File | Item | Severity |
|---|---|---|---|
| 12 | `query/engine.py` | `effective_question` — collapse ALL Unicode whitespace (`\s+` via `re.sub`) not just `\n`/`\r` | LOW (R4) |
| 13 | `query/engine.py` | `search_raw_sources` — strip YAML frontmatter via `FRONTMATTER_RE`; `path.stat().st_size > RAW_SOURCE_MAX_BYTES` pre-check BEFORE `read_text`; add `RAW_SOURCE_MAX_BYTES = 2_097_152` to `kb.config`; skip-log `logger.info("search_raw_sources skipped %s: %d bytes > %d cap", path, size, cap)` | MED (R4) |
| 14 | `query/rewriter.py` | `_should_rewrite` — return False for WH-anchored (`who|what|where|when|why|how\b.*\?$`) + proper-noun body | LOW (R4) |
| 15 | `query/dedup.py` | `dedup_results` — `max_results: int | None = None` clamp on output | MED (R4) |
| 16 | `query/hybrid.py` | `hybrid_search` — wrap `bm25_fn()` and `vector_fn()` in try/except returning `[]` with structured WARN log `logger.warning("hybrid_search backend=%s failed: %s (%s); query_tokens=%d", backend_name, exc.__class__.__name__, exc, len(question.split()))` | HIGH (R4) |
| 17 | `query/citations.py` | `extract_citations` — dedup by `(type, path)`, preserve first context | LOW (R1) |

### evolve / lint — 6 items, 3 files

| # | File | Item | Severity |
|---|---|---|---|
| 18 | `evolve/analyzer.py` | `find_connection_opportunities` — filter numeric-only tokens | MED (R2) |
| 19 | `evolve/analyzer.py` | `find_connection_opportunities` — strip `[[...]]` wikilink markup before tokenising | MED (R4) |
| 20 | `evolve/analyzer.py` | Narrow over-broad `ImportError, AttributeError, OSError, ValueError` catch → `KeyError, TypeError` | MED (R4) |
| 21 | `lint/trends.py` | `compute_verdict_trends` — add `parse_failures` counter; surface in returned dict | MED (R5) |
| 22 | `lint/trends.py` | `_parse_timestamp` — drop vestigial `ValueError` try/except (project pins Py3.12+) | LOW (R4) |
| 23 | `lint/semantic.py` | `_group_by_term_overlap` — import shared `FRONTMATTER_RE` from `utils.markdown` | LOW (R4) |

### feedback / compile / graph / ingest — 5 items, 5 files

| # | File | Item | Severity |
|---|---|---|---|
| 24 | `feedback/store.py` | `load_feedback` — one-shot schema migration; drop per-write `setdefault` loop | LOW (R4) |
| 25 | `feedback/reliability.py` | `get_coverage_gaps` — dedup keep entry with longest/newest notes | MED (R2) |
| 26 | `compile/linker.py` | `inject_wikilinks` — single `_FRONTMATTER_RE.match`, reuse for body-check and split | MED (R4) |
| 27 | `graph/export.py` | `export_mermaid` — deterministic tie-break `(degree desc, id asc)` in auto-prune | MED (R2) |
| 28 | `ingest/evidence.py` | `format_evidence_entry` (RENDER path) — backtick-wrap `source_ref` in rendered markdown cell only; `build_evidence_entry` stays byte-for-byte | LOW (R4) |
| 29 | `utils/wiki_log.py` | Open log in `"a"` mode with `encoding="utf-8", newline="\n"` — forces LF line endings on Windows; pairs with items 8-9 in same commit | MED (R4) |
| 30 | `query/dedup.py` | `dedup_results` layer 2 — fall back to `r.get("content_lower") or r.get("content", "")` when pre-lowered missing; pairs with item 15 in same commit | MED (R4) |

**Total: 30 items, 19 files.** (Items 29/30 rides along in existing commits — no new commits added.)

## Threat model summary

Step 2 threat model identified these trust-boundary items (Step 11 must verify):

- **Audit trail** (`wiki_log.py`): escape must preserve message text; `FileExistsError` branch must re-run regular-file check.
- **Data durability** (`io.py` fsync): must RAISE on `OSError` from fsync/flush; must NOT mask write failure. Cleanup WARNING must not mask the original exception.
- **Third-party API surface** (`llm.py`): `LLMError` truncation must preserve type / model / status code. Jitter must not be double-applied.
- **LLM response parsing** (`call_llm_json`): multi-tool-use must be detected, leading text surfaced on no-tool-use.
- **Raw-source integrity** (`engine.py`): frontmatter strip must not cross into wiki/; 2MB cap must log skip reason with path.
- **Retrieval-backend isolation** (`hybrid.py`): try/except must log backend, exception type, token count.
- **Provenance parsing** (`evidence.py`): backtick wrap must affect rendered table cell only, not the stored `source:` field.
- **Log observability** (`io.py`, `hybrid.py`, `trends.py`): no silent `DEBUG` swallows where operator needs to know.

## Test strategy

- One parametrised regression test per item in `tests/test_backlog_by_file_cycle2.py` — exercises the
  production code path (not the signature — per `feedback_test_behavior_over_signature`).
- Items touching already-tested functions extend their canonical test file rather than adding
  a versioned one (R3 "coverage-visibility" concern from BACKLOG).
- LLM paths mocked at `call_llm` / `_make_api_call`; no live API calls.
- Threading / multiprocessing tests avoided (covered by R3 "multiprocessing deferred to own cycle").

## Acceptance criteria

1. Every shipped fix traces to an item # above.
2. `python -m pytest` green; `ruff check src/ tests/` + `ruff format --check src/ tests/` green.
3. Each behaviour-changing item has a regression test.
4. CHANGELOG `[Unreleased]` gains one bullet per shipped item; BACKLOG deletes resolved lines.
5. PR body enumerates items by file with severity + round tag.
6. No destructive ops, no secrets, no `--no-verify`.

## Dependency ordering (implementation)

Start with leaf files (no intra-batch imports) → higher-coupling files last:

1. `utils/hashing.py`, `utils/markdown.py`, `utils/wiki_log.py`, `utils/io.py`, `utils/llm.py`
2. `ingest/evidence.py`, `compile/linker.py`
3. `feedback/store.py`, `feedback/reliability.py`
4. `evolve/analyzer.py`, `lint/trends.py`, `lint/semantic.py`
5. `graph/export.py`
6. `query/citations.py`, `query/hybrid.py`, `query/dedup.py`, `query/rewriter.py`, `query/engine.py`

Each file = one commit (`fix(<file>): <short summary>`) with its BACKLOG/CHANGELOG doc update included.

## Risk register

- `call_llm_json` multi-tool-use change: existing callers assume single-tool-use — verify `extract_from_source`, `rewrite_query`, `detect_contradictions` all pass a single-tool schema.
- `dedup_results` clamp: current callers pre-clamp; post-clamp must not double-truncate. Test both.
- `wiki_log` escape: must NOT break `wiki/log.md` readability for existing entries (backwards-compatible).
- `evidence.py` pipe escape: applied at RENDER time only; stored entries remain byte-for-byte identical to prior format.
- `io.py` encoding=ascii: legacy utf-8 locks purged at module-load by `_purge_legacy_locks` (one-time idempotent migration). Regression test: seed `.data/locks/x.lock` with `b'\xe2\x98\x83'`, import module, assert file removed.
- `query/engine.py` `\s+` collapse: BM25-path only; rewriter memoisation keys on original `question` string; vector cache keys on post-rewrite text. Regression asserts identical cache state for pre/post whitespace-normalised input.

## Out-of-scope verified (grep-confirmed open)

Before committing scope, spot-checked that cycle 1 didn't already fix these:

- `utils/llm.py` jitter — not in CHANGELOG cycle 1
- `query/dedup.py` max_results clamp — only `_content_tokens` cache was closed
- `query/hybrid.py` bm25/vector wrap — only expand_fn was wrapped
- `evolve/analyzer.py` numeric tokens — confirmed still open

## Step 5 decisions (see `docs/superpowers/decisions/2026-04-17-backlog-by-file-cycle2-design.md`)

All 11 open questions resolved by Opus gate (auto-approve). Scope finalized at 30 items / 19 files.
Follow-up BACKLOG entries filed for: `LLMError` BadRequestError redaction (LOW, next cycle),
`review/refiner.py` two-phase write (HIGH, dedicated cycle), vector-index lifecycle cycle.
