---
title: "Cycle 7 — backlog-by-file — requirements"
date: 2026-04-18
type: requirements
feature: backlog-by-file-cycle7
---

# Cycle 7 — Backlog-by-file — Requirements

## Problem

30 BACKLOG items across 22 files remain open (HIGH + MEDIUM + LOW) after cycle 6 merged. Items are low-blast-radius code-quality fixes that can be shipped in parallel per the user's file-grouped batching convention. Scope: tactical bug fixes + signature-preserving improvements + documentation updates — no architectural rewrites.

## Non-goals

- NOT architectural: no manifest receipt system, no wiki-wide write lock, no sync→async MCP refactor, no config.py split, no compile→pipeline rename.
- NOT new features: no Phase 5 items from the community-followup section.
- NOT test-infrastructure overhauls: no snapshot-testing migration, no fixture consolidation beyond the single conftest.py autouse reset.
- NOT public API changes: existing function signatures must remain compatible (new `pages=` params are optional; new helpers are additive).

## Acceptance Criteria

Every AC below is a testable pass/fail. File list = blast radius (Step 1 → Step 8 coverage check reference).

### Tests / infrastructure (1 item)

- **AC1** (`tests/conftest.py`) — add autouse fixture calling `kb.query.embeddings._reset_model()` and clearing `_index_cache` between tests to prevent module-level singleton leak across tests. Verify by: at least one test that previously was order-dependent on `_model` now passes in isolation AND in the full suite.

### Query engine + embeddings (3 items)

- **AC2** (`src/kb/query/embeddings.py:168` `embed_texts`) — drop the `[vec.tolist() for vec in embeddings]` round-trip; pass the numpy array (each `vec` is a numpy row) directly to `sqlite_vec.serialize_float32` via the buffer protocol. Verify by: behavioural test asserting `embed_texts(["a","b"])` returns 2-element list where each element is bytes (or numpy), and `VectorIndex.build(...)` round-trips unchanged rows.
- **AC3** (`src/kb/query/embeddings.py:32` `_index_cache`) — bound the dict at `MAX_INDEX_CACHE_SIZE=8` entries with FIFO eviction protected by `_index_cache_lock`. Verify by: test inserting >8 entries asserts only 8 remain AND the oldest is evicted.
- **AC4** (`src/kb/query/engine.py:632` `query_wiki` docstring) — document the `stale` key on citations + the `stale_citations: list[str]` return field (present at line 822/825 but undocumented). Verify by: docstring grep assertion on key names in `query_wiki.__doc__`.

### Ingest pipeline (5 items)

- **AC5** (`src/kb/ingest/pipeline.py:487` `_update_existing_page`) — References regex: normalize `body_text` to end with `\n` before running substitution so References-as-last-section pages no longer have new refs prepended rather than appended. Verify by: page with `## References\n- ref1` (no trailing newline) receives new ref ordered AFTER ref1.
- **AC6** (`src/kb/ingest/pipeline.py:948,982` bare-except) — narrow the outer `except Exception as e:` at the contradiction-detection / ingest-tail sites to `(KeyError, TypeError, re.error, AttributeError)` + promote to `logger.warning` with `source_ref` context (re-raise on any other exception to surface bugs). Verify by: raising `ValueError` inside the wrapped block surfaces the exception (test via monkeypatch).
- **AC7** (`src/kb/ingest/pipeline.py:345-360` `_update_existing_page` context enrichment) — when context already present, append new `### From {source_ref}` subsection under existing `## Context` header rather than skip the new context. Verify by: ingest same entity from source A then source B with different context strings; final page contains BOTH `### From raw/articles/a.md` and `### From raw/articles/b.md`.
- **AC8** (`src/kb/ingest/pipeline.py:66-90` `_find_affected_pages`) — when caller passes preloaded `pages=`, thread them into the internal `build_backlinks` call (currently pays a full disk re-walk). Verify by: test patches `kb.compile.linker.scan_wiki_pages` with a spy; `ingest_source(...)` now calls it AT MOST once across the full ingest.
- **AC29** (`src/kb/ingest/pipeline.py:134-151` `_write_wiki_page`) — replace hand-rolled f-string YAML frontmatter with `frontmatter.Post(content=content, **metadata)` + `frontmatter.dumps(post)` for consistency with page-read codepath. Verify by: round-trip test writes-then-reads a page whose title contains YAML-special chars (`"`, `:`, `\n`).

### Lint (4 items)

- **AC14** (`src/kb/lint/checks.py:485-521` `check_source_coverage`) — short-circuit with `logger.warning` when `content` does not start with `---\n` (missing frontmatter fence), emitting a `frontmatter_missing` issue instead of silently dropping any declared sources. Verify by: page whose body is plain markdown (no frontmatter) produces a `frontmatter_missing` issue AND is NOT also double-reported as "no source ref".
- **AC18** (`src/kb/lint/checks.py` `check_dead_links`) — when link target is a root-level index file (`index.md`/`_sources.md`/`log.md`/`_categories.md`), skip the dead-link flag. Verify by: fixture wiki with a page linking `[[index]]` no longer raises a dead-link issue.
- **AC19** (`src/kb/lint/semantic.py:86-102,105-109,112-216` `_group_by_*`) — extend `build_consistency_context(pages=None, ...)` and thread a `pages_bundle` through all three `_group_by_*` helpers, matching the runner.py `shared_pages` pattern. Verify by: spy on `scan_wiki_pages` inside `build_consistency_context(pages=mypages)` asserts zero additional filesystem walks.
- **AC20** (`src/kb/lint/verdicts.py:60-90` `load_verdicts`) — add single retry after 50 ms when `path.stat()` or `path.read_text()` raises `OSError` (atomic-rename window on Windows). Verify by: test that injects one `OSError` on first `read_text` call, second call succeeds; returns list.
- **AC27** (`src/kb/lint/runner.py:110-119` verdict-summary + 1 more site) — introduce a `_safe_call(fn, *, fallback, label)` helper and route the verdict_history degradation site + one more silent-degradation site through it; returned report includes `{label}_error: <msg>` on failure. Verify by: raising `OSError` inside a patched `get_verdict_summary` surfaces `verdict_history_error` in the returned report dict.

### Evolve / graph / compile-linker (3 items — threading cluster)

- **AC9** (`src/kb/evolve/analyzer.py:112,246` `generate_evolution_report`) — thread `pages=` into `build_backlinks` + `build_graph` sub-calls so the preloaded list at line 38/114 is re-used (currently drops the saving by calling bare `build_graph(wiki_dir)`). Verify by: spy-test asserts `scan_wiki_pages` called only once across one `generate_evolution_report(pages=mypages)` invocation.
- **AC10** (`src/kb/compile/linker.py:108-139` `build_backlinks`) — add optional `pages: list[dict] | None = None` parameter; when provided, skip the internal `scan_wiki_pages` walk. Verify by: spy asserts zero filesystem walk when `pages=` is supplied; default path unchanged.
- **AC11** (`src/kb/graph/builder.py` `build_graph`) — add optional `pages: list[dict] | None = None` parameter; skip internal walk when supplied. Verify by: spy asserts zero filesystem walk when `pages=` is supplied; default path unchanged.

### MCP error-string leak (2 items)

- **AC12** (`src/kb/mcp/core.py:183,350,504,553,732` error-string sites) — route raw `{e}` exception interpolations through `_rel()`-preprocessing so Windows absolute paths never reach the MCP client. Verify by: patched failure in each site returns a string that does NOT contain `D:\\` / `/home/`.
- **AC13** (`src/kb/mcp/health.py:62,93,113,166,183` error-string sites) — same treatment. Verify by: same test pattern per site.

### Review + context (2 items)

- **AC21** (`src/kb/review/context.py:15-60` `pair_page_with_sources`) — accept `project_root: Path | None = None` parameter; stop deriving from `raw_dir.parent`. Verify by: supplying an arbitrary `raw_dir` + explicit `project_root` no longer gives wider traversal surface than the explicit root.
- **AC22** (`src/kb/review/refiner.py:82-96` `refine_page`) — before rewriting frontmatter, parse the block with `yaml.safe_load`; reject refine with error on malformed YAML so corrupt frontmatter isn't laundered through a successful write. Verify by: page with malformed frontmatter triggers `Error: malformed frontmatter YAML` instead of returning success.

### Extractors + config + CLI (4 items)

- **AC23** (`src/kb/ingest/extractors.py:274-276` `build_extraction_prompt`) — wrap `wrapped` in `<kb_focus>...</kb_focus>` XML sentinel (`wrap_purpose` already caps at 4096 chars so length is safe). Verify by: generated prompt contains `<kb_focus>` AND `</kb_focus>` around the wrapped purpose text; absent when purpose is empty.
- **AC24** (`src/kb/config.py:88-92` `MODEL_TIERS`) — add `get_model_tier(tier: str) -> str` that re-reads env on every call; keep the `MODEL_TIERS` dict as a legacy read-once mirror. Verify by: test sets `CLAUDE_SCAN_MODEL=test-x`, calls `get_model_tier("scan")`, gets `"test-x"`; mutates env again, re-calls, gets updated value.
- **AC16** (`src/kb/cli.py:52,138,258,293`) — standardize exit on `sys.exit(1)` for errors and `sys.exit(0)` for warnings; document the contract at the top-level docstring. Verify by: test calls `kb compile` with injected error path; `SystemExit(1)` raised (not `click.exceptions.Exit(1)`).
- **AC30** (`src/kb/cli.py:3-8`) — short-circuit `--version` before Click machinery: `if len(sys.argv)==2 and sys.argv[1]=="--version": print(__version__); sys.exit(0)`. Verify by: timing-free test — patching `kb.config` import raises; `kb --version` still succeeds because config was never imported.

### Other refinements (5 items)

- **AC15** (`tests/test_phase4_audit_compile.py:6-43` `test_manifest_pruning_keeps_unchanged_source`) — assert `_template/article` sentinel preserved alongside existing source-entry assertions. Verify by: the new assert lands on the test at or near current end-of-test.
- **AC17** (`src/kb/utils/io.py` module docstring) — document global lock-acquisition convention `(VERDICTS → FEEDBACK → HISTORY)` in alphabetical order at module top. Verify by: docstring grep for `Lock-ordering convention`.
- **AC25** (`CLAUDE.md`) — add a subsection `### Evidence Trail Convention` under the Phase 4 feature list documenting the top-prepend (reverse-chronological) insert-after-sentinel behaviour that `append_evidence_trail` implements. Verify by: grep `Evidence Trail Convention` in CLAUDE.md.
- **AC26** (`src/kb/graph/export.py:157-159` title fallback) — when `_sanitize_label` returns empty, use `node.split("/")[-1]` for the LABEL (display text) without running it through `_safe_node_id` (which replaces `-` with `_` — incorrect for human-readable text). Verify by: test with node `entities/foo-bar` and empty sanitized label produces label `foo-bar` (with dash), not `foo_bar`.
- **AC28** (`src/kb/ingest/extractors.py:64-91,191-199` `clear_template_cache`) — guard `clear_template_cache()` with a `threading.Lock` so cache-clear cannot race with in-flight `_load_template_cached()` readers. Verify by: stress test with 4 concurrent threads each calling `_build_schema_cached` + 1 thread calling `clear_template_cache()` — no `RuntimeError: dictionary changed size during iteration`.

## Blast radius (files touched)

```
src/kb/query/embeddings.py   (AC2, AC3)
src/kb/query/engine.py       (AC4)
src/kb/ingest/pipeline.py    (AC5, AC6, AC7, AC8, AC29)
src/kb/ingest/extractors.py  (AC23, AC28)
src/kb/lint/checks.py        (AC14, AC18)
src/kb/lint/semantic.py      (AC19)
src/kb/lint/verdicts.py      (AC20)
src/kb/lint/runner.py        (AC27)
src/kb/evolve/analyzer.py    (AC9)
src/kb/compile/linker.py     (AC10)
src/kb/graph/builder.py      (AC11)
src/kb/graph/export.py       (AC26)
src/kb/mcp/core.py           (AC12)
src/kb/mcp/health.py         (AC13)
src/kb/review/context.py     (AC21)
src/kb/review/refiner.py     (AC22)
src/kb/config.py             (AC24)
src/kb/cli.py                (AC16, AC30)
src/kb/utils/io.py           (AC17)
tests/conftest.py            (AC1)
tests/test_phase4_audit_compile.py  (AC15)
CLAUDE.md                    (AC25)
```

22 files · 30 acceptance criteria.

## Existing guards (design-informing)

- 1870 passing tests in cycle 6 baseline — no regressions allowed.
- Ruff check + format clean on current main.
- `tests/conftest.py` has `tmp_wiki` + `tmp_project` + `create_wiki_page` + `create_raw_source` fixtures — use them instead of manual scaffolding.
- Commit convention: one commit per file (user's batch-by-file memory).
- PR review convention: 3 rounds for batches > 25 items (user's 3-round PR review memory).
- Red flags to re-check at Steps 7/8/9/11/14: signature drift, inspect-source tests, migration breaking negative-asserts, ruff autofix removing monkeypatched imports, helper orphaning, thread-safety ≠ lock-around-init, plan-gate on summary, `re.findall` source-scan tests.
