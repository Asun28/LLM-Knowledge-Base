# Cycle 15 — Requirements + Acceptance Criteria

**Status:** Draft (Step 1)
**Date:** 2026-04-20
**Cycle type:** Backlog-by-file batch (grouped wiring-and-consumer follow-ups from cycle 14)
**Scope target:** 32 ACs across 9 source files + 13 new test files + 3 doc files (~25 file touch)

## Problem

Cycle 14 shipped the vocabulary + helpers for three epistemic-integrity features (`belief_state` / `authored_by` / `status`, per-platform `decay_days_for`, tier-1 `tier1_budget_for`, publish module) but deferred call-site wiring. Consumers still use the flat `STALENESS_MAX_DAYS`, the hardcoded `CONTEXT_TIER1_BUDGET`, and `out_path.write_text` non-atomic writes. The publish module regenerates unconditionally; `status` and `authored_by` have no lint/evolve/query consumers. This cycle ships the wiring + the per-topic volatility multiplier that BACKLOG.md §Medium-Leverage flags as unshipped.

## Non-goals

- LLM-suggested rephrasings for low-coverage advisory (requires LLM-cost design — defer to cycle 16+).
- Cross-reference auto-linking (new algorithm — defer).
- `kb_query save_as` parameter (new MCP surface area — defer).
- Inline `[!contradiction]` / `[!gap]` / `[!stale]` callout markers in ingest (prompt rewrite — defer).
- Duplicate-slug lint check (requires distance metric — defer).
- Compile-time auto-publish hook + per-page sibling `.txt`/`.json` + `/sitemap.xml` (larger scope — defer).
- Two-phase publish / pre-publish gate (design change — Phase 6 candidate).
- HIGH concurrency cluster (manifest races, inject_wikilinks locks, slug collisions) — explicit non-goal; needs dedicated cycle with cross-process tests.

## Acceptance Criteria (32)

Each testable pass/fail. Tests colocated in `tests/test_cycle15_*.py`; baseline = 2245 passing.

### Query engine (AC1-AC3) — `src/kb/query/engine.py`

- **AC1:** `_flag_stale_results` (engine.py:366) reads `source_ref` per result and calls `decay_days_for(source_ref)` instead of the flat `STALENESS_MAX_DAYS`. Pages with no `source:` field fall back to `SOURCE_DECAY_DEFAULT_DAYS`. Stale-flag result is identical for pages whose source matches default (90d). New source files (arxiv.org → 1095d) see older-but-not-stale pages unflagged.

- **AC2:** `_build_query_context` (engine.py:636) tier-1 loop uses `tier1_budget_for("summaries")` instead of reading `CONTEXT_TIER1_BUDGET` directly. Assertion: `tier1_budget_for("summaries") == (CONTEXT_TIER1_BUDGET * 60) // 100` given the 60/20/5/15 split; code path must call the helper.

- **AC3:** New `_apply_authored_by_boost(page)` helper, applied after `_apply_status_boost` in the score pipeline (engine.py:248). Pages with `authored_by in {"human", "hybrid"}` receive a `score *= (1 + AUTHORED_BY_BOOST)` multiplier; `AUTHORED_BY_BOOST = 0.02` in config. Invalid `authored_by` → no boost. Ungated on `validate_frontmatter` pass (same as `_apply_status_boost`).

### Lint checks (AC4-AC7) — `src/kb/lint/checks.py`

- **AC4:** `check_staleness` (checks.py:299) per-page `max_days` uses `decay_days_for(source_ref)` instead of the flat argument. Callers can still override via `max_days` kwarg (takes precedence). Default path (no override) reads each page's `source:` field.

- **AC5:** New `check_status_mature_stale(pages, today=None)` — flags pages with `status: mature` whose `updated` date is more than 90 days older than `today`. Emits `level: "warning", check: "status_mature_stale", message: "mature page {pid} unchanged {N} days — consider re-review"`.

- **AC6:** New `check_authored_by_drift(pages)` — flags pages where `authored_by: human` AND the Evidence Trail section contains at least one entry with `action: ingest` (regex match, not YAML parse). Emits `level: "warning", check: "authored_by_drift", message: "human-authored {pid} auto-edited by ingest — drop authored_by or change to hybrid"`.

- **AC7:** `run_all_checks` in `lint/runner.py` wires AC5 + AC6 checks into its check list (idempotent; same report format).

### Evolve (AC8) — `src/kb/evolve/analyzer.py`

- **AC8:** `suggest_new_pages` (analyzer.py:195) stable-sorts its output so pages with `status: seed` come first. Secondary sort key: existing score. Pages without `status` sort after `seed` but before `mature|evergreen`. Test: feed 4 pages (seed / developing / mature / missing) → seed emerges first.

### Publish (AC9-AC12) — `src/kb/compile/publish.py`

- **AC9:** `build_llms_txt` replaces `out_path.write_text(...)` with `atomic_text_write(content, out_path)` import from `kb.utils.io`. Crash between temp + rename leaves no partial output.

- **AC10:** `build_llms_full_txt` same change — `atomic_text_write` wrapping. The existing UTF-8 byte-cap loop is unchanged; only the final write is migrated.

- **AC11:** `build_graph_jsonld` uses temp-file + `os.replace` pattern instead of `json.dump` direct to path. Concurrent readers see either old or new file, never a half-serialised one.

- **AC12:** New `_publish_skip_if_unchanged(wiki_dir, out_path)` helper. `build_llms_txt` / `build_llms_full_txt` / `build_graph_jsonld` each accept an `incremental: bool = False` kwarg; when True + `out_path.exists()` + `max(page.stat().st_mtime for page in wiki_dir iterator) <= out_path.stat().st_mtime`, the function short-circuits and returns `out_path` without reopening any content. Default False preserves existing test contract.

### CLI (AC13) — `src/kb/cli.py`

- **AC13:** `kb publish` accepts `--incremental / --no-incremental` Click option (default `--incremental`). All three builders called with `incremental=<flag>`. `--no-incremental` forces regeneration.

### Config (AC14-AC16) — `src/kb/config.py`

- **AC14:** `SOURCE_VOLATILITY_TOPICS: dict[str, float] = {"llm": 1.1, "react": 1.1, "docker": 1.1, "claude": 1.1, "agent": 1.1, "mcp": 1.1}`. Keys are case-folded substrings matched against page tags/title.

- **AC15:** `volatility_multiplier_for(text: str | None) -> float` helper. Returns `1.0` when `text is None`/empty; case-insensitive word-boundary search for any key in `SOURCE_VOLATILITY_TOPICS`; returns the max matched multiplier or `1.0`. Non-boundary substring matches (e.g., `reactor` containing `react`) must NOT fire — use `re.search(r"\b<key>\b", ..., re.IGNORECASE)`.

- **AC16:** `decay_days_for(ref, topics=None)` accepts optional `topics: str | None` kwarg. When provided, result = `int(base_days * volatility_multiplier_for(topics))`. Default `None` preserves backward-compat (no multiplier). Call sites (AC1, AC4) pass `topics=page.get("tags", "") + " " + page.get("title", "")`.

### Augment (AC17) — `src/kb/lint/augment.py`

- **AC17:** `_post_ingest_quality` (augment.py:1108) switches from `frontmatter.load(str(...))` to `load_page_frontmatter(page_path)` preceded by `load_page_frontmatter.cache_clear()` when called from the augment write-back path. Rationale: same-process writes from `_mark_page_augmented` / `_record_verdict_gap_callout` happen seconds before; cache must be invalidated explicitly. FAT32/OneDrive/SMB stale-read concern documented in cycle-13 comment stays.

### Loader (AC18-AC19) — `src/kb/utils/pages.py`

- **AC18:** `load_all_pages` returns additive `authored_by` key — empty string when absent. Mirrors cycle-14 `status` pattern. Closes cycle-14 L3 loader-side atomicity gap for the remaining two vocabulary fields.

- **AC19:** `load_all_pages` returns additive `belief_state` key — empty string when absent. Same shape as AC18.

### Tests (AC20-AC32) — `tests/test_cycle15_*.py`

- **AC20:** `test_cycle15_query_decay_wiring.py` — seeds pages with `source: arxiv.org/...` (decay=1095d) vs `github.com/...` (decay=180d); asserts `_flag_stale_results` respects per-source decay.

- **AC21:** `test_cycle15_query_tier1_wiring.py` — monkeypatches `CONTEXT_TIER1_SPLIT["summaries"]` to 10, asserts the tier-1 summaries budget in `_build_query_context` shrinks correspondingly (proves call-site uses the helper).

- **AC22:** `test_cycle15_authored_by_boost.py` — asserts boost applied to human/hybrid, not applied to llm or absent; invalid `authored_by: robot` → no boost, no raise.

- **AC23:** `test_cycle15_lint_decay_wiring.py` — `check_staleness` respects per-platform decay (arxiv page 1000d old not flagged; github page 200d old flagged).

- **AC24:** `test_cycle15_lint_status_mature.py` — mature page 91d old flagged; mature page 89d not flagged; seed/developing pages ignored.

- **AC25:** `test_cycle15_lint_authored_drift.py` — human page with ingest evidence entry flagged; hybrid page with ingest entry not flagged; human page with only `action: edit` entries not flagged.

- **AC26:** `test_cycle15_evolve_status_seed.py` — `suggest_new_pages` returns seed-status pages before mature pages.

- **AC27:** `test_cycle15_publish_atomic.py` — asserts the three builders call `atomic_text_write` (spy via `monkeypatch.setattr("kb.compile.publish.atomic_text_write", spy)`) and not `Path.write_text` directly.

- **AC28:** `test_cycle15_publish_incremental.py` — second call with `incremental=True` short-circuits when all wiki pages older than output mtime; forced `incremental=False` regenerates; mtime-freshening a page re-triggers write.

- **AC29:** `test_cycle15_cli_incremental.py` — `kb publish --no-incremental` regenerates; `kb publish` (default) uses incremental; CliRunner.invoke + capsys.

- **AC30:** `test_cycle15_config_volatility.py` — `SOURCE_VOLATILITY_TOPICS` present; `volatility_multiplier_for` boundary match ("llm" fires; "reactor" does not); `decay_days_for("arxiv.org", topics="LLM agents")` returns `int(1095 * 1.1) = 1204`.

- **AC31:** `test_cycle15_augment_cache_clear.py` — simulate `_mark_page_augmented` write + `_post_ingest_quality` call; assert it sees the post-write metadata (cache invalidation path works).

- **AC32:** `test_cycle15_load_all_pages_fields.py` — `load_all_pages` returns dicts with `authored_by` and `belief_state` keys for pages with and without those fields.

### Docs (not ACs, Step 12 outputs)

- CHANGELOG.md: cycle 15 entry under `[Unreleased]`.
- BACKLOG.md: delete 8 closed entries (decay_days_for wiring, tier1_budget_for wiring, status evolve/lint sub-asks, authored_by consumers, _post_ingest_quality cache, atomic publish writes, incremental publish, per-topic volatility multiplier). Adds cycle-16 follow-up: LLM rephrasings, cross-reference auto-linking, kb_query save_as, callout markers, duplicate-slug lint, compile-time auto-publish.
- CLAUDE.md: stats bump (tool count unchanged, test count updated), cycle-15 notes under `## Implementation Status` for the wiring items.

## Blast radius

Affected modules: `src/kb/query/engine.py`, `src/kb/lint/checks.py`, `src/kb/lint/runner.py`, `src/kb/lint/augment.py`, `src/kb/evolve/analyzer.py`, `src/kb/compile/publish.py`, `src/kb/cli.py`, `src/kb/config.py`, `src/kb/utils/pages.py`. Thirteen new test files. Zero new production dependencies; zero new MCP tools; no changes to extraction prompts or ingest pipeline. All AC changes are either (a) substituting a helper for a hardcoded value at an existing call site, or (b) adding a new lint/evolve check behind `run_all_checks`/`suggest_new_pages` — backward-compatible in shape, opt-in by default.

## Prerequisite greps (Step 1 verification)

Confirmed before writing ACs (all exist in source today):

- `decay_days_for` — config.py:382 (helper) — NOT YET wired in engine.py:366 (`_flag_stale_results`) or checks.py:299 (`check_staleness`). Confirmed.
- `tier1_budget_for` — config.py:350 (helper) — NOT YET wired in engine.py:636 (`_build_query_context`) which reads `CONTEXT_TIER1_BUDGET` direct. Confirmed.
- `STATUS_RANKING_BOOST` — config.py:425 + engine.py:313 via `_apply_status_boost`. Model for AC3 (`_apply_authored_by_boost`).
- `load_page_frontmatter` — utils/pages.py (cycle 12 LRU-cached helper with mtime_ns key) — used in augment but not `_post_ingest_quality` (which per cycle-13 comment intentionally stays on `frontmatter.load`). AC17 changes that.
- `out_path.write_text` — publish.py uses this directly; confirmed absent of `atomic_text_write`. AC9-11 fix.
- `load_all_pages` — utils/pages.py:164 currently emits only `status` as additive; `authored_by` and `belief_state` missing. AC18-19 fix.
- `suggest_new_pages` — evolve/analyzer.py:195 — no `status` key consideration. AC8 fix.
- `check_staleness` — lint/checks.py:299 — uses flat `STALENESS_MAX_DAYS`. AC4 fix.
- `SOURCE_VOLATILITY_TOPICS` — does NOT exist. New in AC14.

## Exit criteria

- All 32 ACs pass dedicated regression tests.
- `python -m pytest` green: 2245 → ~2280 expected (baseline + 32 new assertion-bearing tests, accounting for some AC bundling).
- `ruff check src/ tests/` clean.
- `ruff format --check src/ tests/` clean.
- PR merged to main with 2–3 review rounds per batch-size guardrail.
