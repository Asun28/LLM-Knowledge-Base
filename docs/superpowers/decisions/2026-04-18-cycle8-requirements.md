# Cycle 8 — Requirements + Acceptance Criteria

**Date:** 2026-04-18
**Branch:** feat/backlog-by-file-cycle8
**Target scope:** 30 AC across 19 files (12 source + 7 new test files)

## Problem

BACKLOG.md still carries ~11 concrete fixable items from Phase 4.5 HIGH / MEDIUM /
LOW audits + Phase 5 deferred work. Prior cycles 1–7 shipped file-adjacent
groups (all verified against current source before starting). Cycle 8 continues
the file-grouped cadence: curate the top-level package surface, promote the
dead model dataclasses to real validated types, add LLM call telemetry on
success, close three MCP `wiki_dir` plumbing holes, cap `kb_lint_consistency`
auto-mode output so large wikis don't blow the MCP transport, lift PageRank
from a post-fusion multiplier to a rank-level RRF signal, make
`_persist_contradictions` idempotent, and consolidate notes-length validation
at the MCP boundary.

## Non-goals

- No `file_lock` rewrite to use `msvcrt.locking` (too large; defer).
- No `compile_wiki` two-phase / naming inversion refactor (defer).
- No `config.py` god-module split (defer — risks invalidating cache across the
  whole package during test runs).
- No new feature flags or user-visible CLI arguments (except keyword-only
  `wiki_dir=None` parameters on three MCP tools, mirroring cycle 6).
- No changes to existing public function signatures that would require
  caller-side updates.
- Leave `review/refiner.py` ordering (page → history → log) as-is — the
  pending-audit-first variant is BACKLOG-deferred and out of scope here.

## Blast Radius

Affected modules (by `src/kb/` subdir):
- `kb.__init__`, `kb.utils.__init__`, `kb.models.__init__` — curated
  re-exports (additive; existing `from kb.X.Y import Z` still works).
- `kb.models.page` — adds validators + `to_dict` + `from_post`; existing
  callers (tests only) still construct via kwargs.
- `kb.utils.llm` — adds success telemetry to `_make_api_call`; no public
  signature change.
- `kb.mcp.health`, `kb.mcp.quality` — keyword-only `wiki_dir=None` on three
  tools; no change to existing call sites.
- `kb.lint.semantic` — new total-groups + per-page content caps in auto
  mode; explicit page_ids mode unchanged.
- `kb.config` — adds two constants (`MAX_CONSISTENCY_GROUPS`,
  `MAX_CONSISTENCY_PAGE_CONTENT_CHARS`).
- `kb.query.engine` — reshapes PageRank blending from post-fusion multiply
  to a rank-list input into `rrf_fusion`; behaviour change with observable
  rank-order effects.
- `kb.ingest.pipeline` — `_persist_contradictions` becomes idempotent on
  same-day re-ingest of same source_ref; no change to first-ingest path.
- `kb.mcp.app` — adds `_validate_notes(notes, field_name)` helper; used by
  refine_page revision_notes + kb_query_feedback notes.

## Acceptance Criteria (30)

### Package surface (AC1–AC3)
- **AC1** `src/kb/__init__.py` — re-exports `ingest_source`, `compile_wiki`,
  `query_wiki`, `build_graph`, `WikiPage`, `RawSource`, `LLMError` plus
  `__version__`, with `__all__` listing them. `from kb import <any of those>`
  must succeed in a fresh `python -c`.
- **AC2** `src/kb/utils/__init__.py` — re-exports `slugify`, `yaml_escape`,
  `yaml_sanitize`, `STOPWORDS`, `atomic_json_write`, `atomic_text_write`,
  `file_lock`, `content_hash`, `extract_wikilinks`, `extract_raw_refs`,
  `FRONTMATTER_RE`, `append_wiki_log`, `load_all_pages`, `normalize_sources`,
  `make_source_ref` with `__all__`.
- **AC3** `src/kb/models/__init__.py` — re-exports `WikiPage`, `RawSource`
  with `__all__`.

### WikiPage / RawSource validation (AC4–AC6)
- **AC4** `WikiPage.__post_init__` raises `ValueError` on `page_type not in
  PAGE_TYPES` or `confidence not in CONFIDENCE_LEVELS`; `RawSource.__post_init__`
  raises `ValueError` on `source_type not in VALID_SOURCE_TYPES`.
- **AC5** `WikiPage.to_dict()` returns the JSON wire format: `{"path": str,
  "title": str, "type": str, "sources": list[str], "confidence": str,
  "created": str|None, "updated": str|None, "wikilinks": list[str],
  "content_hash": str|None}` (dates ISO-formatted, Path stringified).
- **AC6** `WikiPage.from_post(post, path)` classmethod accepts a
  `frontmatter.Post`-shaped object + file path and returns a validated
  `WikiPage`. Unknown metadata keys ignored; missing required keys raise
  `ValueError`.

### LLM call telemetry (AC7)
- **AC7** `_make_api_call` logs one INFO-level record per successful return
  with keys `model=<id> attempt=<int> tokens_in=<int|None>
  tokens_out=<int|None> latency_ms=<int>`. Failures still emit the existing
  WARNING path — no regression.

### MCP health tools wiki_dir plumbing (AC8–AC9)
- **AC8** `kb_stats(wiki_dir=None)` accepts an optional override and threads
  it into `analyze_coverage(wiki_dir=...)` + `build_graph(wiki_dir=...)`.
  `wiki_dir=None` preserves the default `kb.config.WIKI_DIR` path.
- **AC9** `kb_verdict_trends(wiki_dir=None)` accepts an optional override;
  derives verdicts path as `wiki_dir.parent / ".data" / "verdicts.json"`
  when provided, else uses `VERDICTS_PATH`. Underlying
  `kb.lint.trends.compute_verdict_trends(path=...)` receives the derived path.

### Consistency context caps (AC10–AC13)
- **AC10** `kb_lint_consistency` docstring documents the new total-groups
  cap + per-page body truncation behaviour in auto mode.
- **AC11** `build_consistency_context(page_ids=None)` auto mode caps total
  emitted groups at `MAX_CONSISTENCY_GROUPS`; excess groups are dropped
  with an INFO log.
- **AC12** `build_consistency_context(page_ids=None)` auto mode truncates
  each inlined page's body to `MAX_CONSISTENCY_PAGE_CONTENT_CHARS` with a
  `\n\n[Truncated at {N} chars — run kb_lint_deep for full body]` marker.
  Explicit `page_ids` mode is unchanged.
- **AC13** `src/kb/config.py` adds `MAX_CONSISTENCY_GROUPS = 20` and
  `MAX_CONSISTENCY_PAGE_CONTENT_CHARS = 4096`.

### PageRank as rank signal (AC14)
- **AC14** `kb.query.engine.search_pages` — when `PAGERANK_SEARCH_WEIGHT > 0`
  and `pagerank_scores` is non-empty, PageRank enters `rrf_fusion` as a
  SEPARATE rank-list input (pages sorted by PageRank descending) INSTEAD
  OF being applied as a post-fusion multiplier. Rank-level blending means
  PageRank competes on equal footing with BM25 + vector rather than only
  tiebreaking at the margin. `rrf_fusion` is called with at least BM25 +
  PageRank lists (and vector when available).

### Contradictions idempotent write (AC15)
- **AC15** `_persist_contradictions` checks if the header block
  `f"\n## {safe_ref} — {today}\n"` is already present in the existing
  contradictions.md content. If present, skip the append (return without
  rewriting). First-ingest path unchanged.

### Notes validation helper (AC16)
- **AC16** `kb.mcp.app._validate_notes(notes, field_name) -> str | None` —
  returns `None` when valid, or `f"Error: {field_name} too long ({n}
  chars; max {MAX_NOTES_LEN})."` when over the cap. `kb_query_feedback`
  and `kb_refine_page` call this once at the MCP boundary instead of
  inlining the check.

### Tests (AC17–AC30)

- **AC17–AC19** `tests/test_cycle8_package_exports.py`
  - AC17: `from kb import ingest_source, compile_wiki, query_wiki,
    build_graph, WikiPage, RawSource, LLMError, __version__` succeeds in
    a fresh subprocess `python -c`.
  - AC18: `from kb.utils import slugify, yaml_escape, atomic_json_write,
    atomic_text_write, file_lock, append_wiki_log, load_all_pages`
    succeeds.
  - AC19: `from kb.models import WikiPage, RawSource` succeeds.
- **AC20–AC23** `tests/test_cycle8_models_validation.py`
  - AC20: `WikiPage(... page_type="bogus")` raises `ValueError`.
  - AC21: `WikiPage(... confidence="certain")` raises `ValueError`.
  - AC22: `WikiPage(...).to_dict()` returns a JSON-serializable dict.
  - AC23: `WikiPage.from_post(post, path)` roundtrips through `to_dict`.
- **AC24** `tests/test_cycle8_llm_telemetry.py` — monkeypatch the
  Anthropic client; assert `caplog` contains one INFO record with
  `model=`, `attempt=`, `tokens_in=`, `tokens_out=`, `latency_ms=`.
- **AC25–AC26** `tests/test_cycle8_health_wiki_dir.py`
  - AC25: `kb_stats(wiki_dir=tmp_wiki)` returns stats scoped to the
    tmp wiki (total_pages matches tmp_wiki page count, not production).
  - AC26: `kb_verdict_trends(wiki_dir=tmp_wiki)` reads from
    `tmp_wiki.parent / ".data" / "verdicts.json"`.
- **AC27–AC28** `tests/test_cycle8_consistency_caps.py`
  - AC27: auto-mode `build_consistency_context()` over a wiki with
    ≥ `MAX_CONSISTENCY_GROUPS + 5` natural groups returns at most
    `MAX_CONSISTENCY_GROUPS` `## Group N` headers.
  - AC28: a page with a body > `MAX_CONSISTENCY_PAGE_CONTENT_CHARS` is
    rendered with the truncation marker.
- **AC29** `tests/test_cycle8_pagerank_prefusion.py` — inject a fake
  BM25 list + fake PageRank scores; assert `rrf_fusion` receives at
  least one rank-list whose order matches PageRank descending (i.e.
  PageRank IS a rank-level input).
- **AC30** `tests/test_cycle8_contradictions_idempotent.py` — call
  `_persist_contradictions` twice with the same `(contradictions,
  source_ref, wiki_dir)` on the same day; assert `contradictions.md`
  contains exactly ONE `## {source_ref} — {today}\n` header.

## Verification Map

| AC | Test file | Assertion shape |
|----|-----------|-----------------|
| AC1 | test_cycle8_package_exports.py::test_kb_top_level_exports | `subprocess.run([python, -c, "from kb import …"])` rc==0 |
| AC2 | test_cycle8_package_exports.py::test_utils_exports | `subprocess.run(...)` rc==0 |
| AC3 | test_cycle8_package_exports.py::test_models_exports | `subprocess.run(...)` rc==0 |
| AC4 | test_cycle8_models_validation.py::test_invalid_page_type | `pytest.raises(ValueError)` |
| AC4 | test_cycle8_models_validation.py::test_invalid_source_type | `pytest.raises(ValueError)` |
| AC5 | test_cycle8_models_validation.py::test_to_dict_shape | `json.dumps(wp.to_dict())` succeeds |
| AC6 | test_cycle8_models_validation.py::test_from_post_roundtrip | `WikiPage.from_post(Post(...), path).to_dict() == expected` |
| AC7 | test_cycle8_llm_telemetry.py::test_success_logs_info_record | `caplog.record_tuples` contains INFO with keys |
| AC8 | test_cycle8_health_wiki_dir.py::test_kb_stats_wiki_dir | tmp_wiki scope |
| AC9 | test_cycle8_health_wiki_dir.py::test_kb_verdict_trends_wiki_dir | path derivation |
| AC10 | test_cycle8_consistency_caps.py docstring check | static |
| AC11 | test_cycle8_consistency_caps.py::test_auto_mode_group_cap | group count <= MAX |
| AC12 | test_cycle8_consistency_caps.py::test_auto_mode_body_truncation | marker present |
| AC13 | test_cycle8_consistency_caps.py::test_config_constants | `from kb.config import MAX_CONSISTENCY_GROUPS, MAX_CONSISTENCY_PAGE_CONTENT_CHARS` |
| AC14 | test_cycle8_pagerank_prefusion.py::test_pagerank_enters_rrf_as_rank_list | `rrf_fusion` spy receives pagerank list |
| AC15 | test_cycle8_contradictions_idempotent.py::test_same_day_reingest_single_block | `file.count("## ...") == 1` |
| AC16 | test_cycle8_consistency_caps.py or existing — `_validate_notes` direct call | helper returns None / Error string |

## Rollback Plan

All AC land in a single feature branch `feat/backlog-by-file-cycle8` rebased
onto `main`. If any AC introduces a regression the reviewer catches,
revert by dropping the specific commit and re-running pytest+ruff. Each
commit is file-scoped (per AC6 file-grouped-commit convention from cycle 4
feedback memory) so reverts are minimal.
