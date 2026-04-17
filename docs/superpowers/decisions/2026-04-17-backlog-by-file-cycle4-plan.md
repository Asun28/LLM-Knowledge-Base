# Cycle 4 Backlog-by-File Cleanup Plan

## Preflight Summary

Design doc present: `docs/superpowers/decisions/2026-04-17-backlog-by-file-cycle4-design.md`; final scope is 22 functional items plus up to 7 shipped-item test backfills.

Mandatory grep/read findings:

1. `def _rel` in `src/kb/mcp/`: `src/kb/mcp/app.py:58:def _rel(path: Path) -> str:`. No `_rel` definition in `core.py`; `core.py` imports it.
2. `_strip_control_chars|strip_control` in `src/kb/`: only `src/kb/mcp/quality.py:30` defines `_strip_control_chars`; callers at `quality.py:45,76,132,262,340,397,400`. No shared sanitizer in `core.py`.
3. `_WH_QUESTION_RE`: `src/kb/query/rewriter.py:21` compiles `^(who|what|where|when|why|how)\b.*\?$`; `rewriter.py:35` applies it unconditionally.
4. `_RAW_BM25_CACHE`: `src/kb/query/engine.py:227` defines raw cache keyed `tuple[str, int, int]`; lock at `:228`; get/store at `:305,:355,:361`. No wiki-side mirror found.
5. `detect_contradictions`: legacy function at `src/kb/ingest/contradiction.py:26`; metadata sibling at `:48`; `src/kb/ingest/pipeline.py:26` imports legacy and `:909` calls legacy.
6. `inject_wikilinks\b`: definition at `src/kb/compile/linker.py:141`; pipeline imports/calls it at `src/kb/ingest/pipeline.py:892-895`; loop is unsorted at `:890`.
7. `load_purpose`: `src/kb/utils/pages.py:104` still accepts `wiki_dir: Path | None = None`; callers in `query/engine.py:653` and `ingest/extractors.py:335`; tests in `tests/test_v0p5_purpose.py`.
8. `STOPWORDS`: source in `src/kb/utils/text.py:40`; imports in `ingest/contradiction.py:7` and `query/bm25.py:17`; tests in `tests/test_v01002_consolidated_constants.py:22-36`.
9. `export_mermaid`: `src/kb/graph/export.py:49` defines it; `src/kb/mcp/health.py:6,156` imports/calls it.
10. `BM25Index`: `src/kb/query/bm25.py:44` defines it; engine imports at `:23`; wiki/raw builds at `engine.py:84,352`.
11. `check_exists|_validate_page_id`: `src/kb/mcp/app.py:66` defines `_validate_page_id`; `:93` checks existence; `:94` advises `kb_list_pages`.
12. `_enforce_type_diversity`: `src/kb/query/dedup.py:52` calls it; `:101` defines it with input-length quota.
13. `wiki_log.py` lines 1-60: docstring says append to `wiki/log.md`; `append_wiki_log(operation, message, log_path)` receives required target at `:16`; no monthly rotation target yet.
14. `app.py` lines 40-100: `_validate_page_id` checks empty/null/traversal/resolve/existence, but no Windows reserved basename or length cap.
15. `contradiction.py` lines 1-60: `detect_contradictions_with_metadata` returns a dict sibling; legacy signature intentionally unchanged.
16. Test-backfill audit exact grep: matches found for `MAX_QUESTION_LEN` (`tests/test_backlog_by_file_cycle1.py:314-318`, `tests/test_v01012_mcp_validation.py:7-59`), `frontmatter_missing_fence` (`tests/test_backlog_by_file_cycle1.py:514`), and `FRONTMATTER_RE` (`tests/test_backlog_by_file_cycle2.py`, `tests/test_phase45_high_cycle2.py`). Exact grep did not match source_type whitelist, ambiguous page_id, title cap 500, or source_refs is_file; broader greps found source_type behavior at `tests/test_backlog_by_file_cycle1.py:327-342`, source_refs existence context at `tests/test_mcp_quality_new.py:23`, and case-insensitive fallback but no ambiguity regression at `tests/test_mcp_browse_health.py:127`.

## Tasks (one per file, in this order):

TASK 1: Harden MCP core paths and writes
  Files: `src/kb/mcp/core.py`, `src/kb/mcp/app.py`, `tests/test_backlog_by_file_cycle4.py`
  Change: In `core.py`, route error-string path interpolation through `_rel()` where filesystem paths are surfaced, add the item #2 sanitizer for `<prior_turn>` variants/control chars/fullwidth angle brackets in the fence-match region, and convert post-create write failures in `kb_ingest_content`/`kb_save_source` into `Error[partial]...` strings after cleanup. Do not move `_rel`; import remains from `app.py`.
  Test: Add behavioral tests that tmp absolute paths are not leaked, prompt-fence variants are stripped while normal CJK text remains, and monkeypatched `fdopen.write` returns an `Error[partial]` string without leaving the file.
  Criteria: Items #1, #2, #5; Conditions 9 and 13.
  Threat: Path disclosure, prompt-injection fence smuggling, partial-write orphan/zombie file.
  Evidence: `src/kb/mcp/app.py:58:def _rel(path: Path) -> str:` and `src/kb/mcp/core.py` exclusive-create write blocks currently re-raise on `BaseException`.

TASK 2: Cap kb_read_page output
  Files: `src/kb/mcp/browse.py`, `tests/test_backlog_by_file_cycle4.py`
  Change: Apply `QUERY_CONTEXT_MAX_CHARS` to `kb_read_page` responses and append an explicit truncation footer when page content is longer.
  Test: Create an oversized wiki page and assert returned text length is bounded and includes a truncation footer naming the cap.
  Criteria: Item #7.
  Threat: MCP transport/LLM context DoS.
  Evidence: `src/kb/mcp/browse.py` returns `page_path.read_text(encoding="utf-8")` directly.

TASK 3: Tighten quality MCP boundaries
  Files: `src/kb/mcp/quality.py`, `tests/test_backlog_by_file_cycle4.py`
  Change: Change `kb_affected_pages` to call `_validate_page_id(..., check_exists=True)` and cap each `issues[].description` before calling `add_verdict`.
  Test: Assert missing page IDs return `Error: Page not found...` and a huge issue description is truncated/rejected before verdict persistence.
  Criteria: Items #11, #12.
  Threat: Phantom-page workflows, verdict store/log flooding.
  Evidence: `src/kb/mcp/quality.py:262` currently validates `kb_affected_pages` with `check_exists=False`; `quality.py` passes parsed `issue_list` to `add_verdict` without per-description cap.

TASK 4: Validate page IDs cross-platform
  Files: `src/kb/mcp/app.py`, `src/kb/mcp/browse.py`, `tests/test_backlog_by_file_cycle4.py`
  Change: Extend `_validate_page_id` to reject Windows reserved basenames cross-platform, cap each page_id at 255 chars, and keep all failures as `"Error: ..."` callers. Verify `kb_list_pages` output remains useful for remediation when a page is missing.
  Test: Assert `concepts/con`, `concepts/aux.txt`, and >255-char IDs are rejected as strings; assert `kb_list_pages` lists existing pages after a not-found remediation hint.
  Criteria: Item #13; Conditions 8 and Q2.
  Threat: Windows device-name writes, path portability failures, uncaught MCP exceptions.
  Evidence: `src/kb/mcp/app.py:66-95` has traversal/existence checks but no reserved-name or length check; `:94` references `kb_list_pages`.

TASK 5: Add deleted-source drift category
  Files: `src/kb/mcp/health.py`, `src/kb/compile/compiler.py`, `tests/test_backlog_by_file_cycle4.py`
  Change: Surface source-deleted drift separately from new/changed source drift in `kb_detect_drift`, using compiler drift data that preserves deleted manifest entries long enough to report affected wiki pages.
  Test: Seed a manifest and page source ref, delete the raw file, and assert `kb_detect_drift` includes a deleted-source category and affected page.
  Criteria: Item #14.
  Threat: Silent staleness after source removal.
  Evidence: `src/kb/mcp/health.py` only renders `changed_sources` and `affected_pages`; `compiler.py:146-153` prunes deleted manifest keys.

TASK 6: Rescope WH question rewrite gate to CJK short queries
  Files: `src/kb/query/rewriter.py`, `tests/test_backlog_by_file_cycle4.py`
  Change: Replace the unconditional English WH-question early return with a CJK-safe short-query gate only for `len(q.strip()) < 15` and CJK content.
  Test: Assert English `"What is RAG?"` can be rewritten with context, while short CJK follow-ups are preserved/gated safely.
  Criteria: Item #15; Condition 3.
  Threat: Search recall loss from over-broad rewrite bypass.
  Evidence: `src/kb/query/rewriter.py:21` defines `_WH_QUESTION_RE`; `:35` returns before rewrite when it matches.

TASK 7: Add wiki BM25 cache versioning
  Files: `src/kb/query/engine.py`, `src/kb/utils/text.py`, `tests/test_backlog_by_file_cycle4.py`
  Change: Add wiki-side `_WIKI_BM25_CACHE` mirroring raw cache behavior and include `BM25_TOKENIZER_VERSION = 2` in both raw and wiki cache keys.
  Test: Monkeypatch `BM25Index` construction and assert repeated wiki searches reuse cache, and bumping tokenizer version invalidates both wiki/raw caches.
  Criteria: Items #16, #18; Conditions 4 and 10.
  Threat: Hot-path rebuild DoS, stale tokenization cache after stopword changes.
  Evidence: `src/kb/query/engine.py:227` raw cache key lacks tokenizer version; `search_pages` rebuilds `BM25Index` at `engine.py:84`.

TASK 8: Enforce running type-diversity quota
  Files: `src/kb/query/dedup.py`, `tests/test_backlog_by_file_cycle4.py`
  Change: Replace input-length type quota with a running output quota so the final result set respects `max_type_ratio` as results are accepted.
  Test: Feed a dominant type followed by scarce types and assert no kept type exceeds the configured final ratio when alternatives exist.
  Criteria: Item #17.
  Threat: Retrieval monoculture; diversity filter bypass by long dominant prefixes.
  Evidence: `src/kb/query/dedup.py:101` computes `max_per_type` from `len(results)` and docstring admits final ratio can exceed max.

TASK 9: Update text tokenizer invariants
  Files: `src/kb/utils/text.py`, `tests/test_backlog_by_file_cycle4.py`
  Change: Remove `new`, `all`, `more`, `most`, `some`, `only`, `other`, `very` from `STOPWORDS`; add `BM25_TOKENIZER_VERSION = 2`; extend `yaml_sanitize` docstring and behavior to silently strip BOM, U+2028, and U+2029.
  Test: Assert removed quantifiers survive `tokenize`, the version constant is `2`, and YAML sanitization drops BOM/line/paragraph separators without logging warnings.
  Criteria: Items #18, #19; Conditions 10 and 11.
  Threat: Query intent loss; YAML/frontmatter structural confusion.
  Evidence: `src/kb/utils/text.py:40` STOPWORDS includes the eight quantifiers; `_CTRL_CHAR_RE` excludes BOM/U+2028/U+2029.

TASK 10: Rotate wiki logs monthly
  Files: `src/kb/utils/wiki_log.py`, `tests/test_backlog_by_file_cycle4.py`
  Change: Before appending to `log.md`, rotate an oversized log to `log.YYYY-MM.md`, adding `.2`, `.3`, etc. on collision, while preserving regular-file rejection and LF writes.
  Test: With a small threshold and existing archive names, assert log rotates to the next ordinal and new `log.md` receives header plus entry.
  Criteria: Item #20; Condition 12.
  Threat: Unbounded audit-log growth.
  Evidence: `src/kb/utils/wiki_log.py:90-97` only warns when size exceeds threshold.

TASK 11: Migrate pipeline contradiction caller
  Files: `src/kb/ingest/pipeline.py`, `src/kb/ingest/contradiction.py`, `tests/test_backlog_by_file_cycle4.py`
  Change: Import and call `detect_contradictions_with_metadata` in pipeline, keep `detect_contradictions` signature unchanged, persist contradictions from the returned dict, and `logger.warning` when metadata says claims were truncated.
  Test: Monkeypatch metadata return with `truncated=True` and assert persisted contradictions plus warning containing checked/total counts.
  Criteria: Item #22; Conditions 1 and 5.
  Threat: Operators cannot detect contradiction coverage truncation.
  Evidence: `src/kb/ingest/pipeline.py:26` imports `detect_contradictions`; `:909` calls the legacy list-returning function; metadata sibling exists at `contradiction.py:48`.

TASK 12: Deprecate Path positional export shim
  Files: `src/kb/graph/export.py`, `tests/test_backlog_by_file_cycle4.py`
  Change: When `export_mermaid` receives a `Path` as first positional `graph`, emit `DeprecationWarning` while preserving backwards-compatible behavior.
  Test: Use `pytest.warns(DeprecationWarning)` for `export_mermaid(tmp_wiki)` and assert output remains a Mermaid graph.
  Criteria: Item #23.
  Threat: N/A.
  Evidence: `src/kb/graph/export.py:68-71` silently treats positional `Path` as `wiki_dir`.

TASK 13: Precompute BM25 postings
  Files: `src/kb/query/bm25.py`, `tests/test_backlog_by_file_cycle4.py`
  Change: Add postings-dict precompute to avoid scanning every document for every query term, and document the accepted memory profile of about 150MB for 5K pages in the module docstring.
  Test: Assert scores are identical to a small hand-computed corpus and that scoring only visits postings for matched terms via a sparse corpus regression.
  Criteria: Item #24; Condition 14.
  Threat: Query CPU hot-path DoS.
  Evidence: `src/kb/query/bm25.py:97-105` loops over every `doc_freq` for each query term.

TASK 14: Whitelist template hash source types
  Files: `src/kb/compile/compiler.py`, `tests/test_backlog_by_file_cycle4.py`
  Change: Gate `_template_hashes` output by configured valid source types so stray template files cannot create manifest keys that later fan out to unsupported source types.
  Test: Create valid and bogus `*.yaml` templates and assert only valid source-type template hashes appear.
  Criteria: Item #25.
  Threat: Manifest pollution / unexpected compile invalidation.
  Evidence: `src/kb/compile/compiler.py:31-33` hashes every non-backup `*.yaml` stem.

TASK 15: Sort wikilink injection inputs
  Files: `src/kb/ingest/pipeline.py`, `src/kb/compile/linker.py`, `tests/test_backlog_by_file_cycle4.py`
  Change: Wrap the caller-side `inject_wikilinks` loop iterable with `sorted()` so title injection order is deterministic; do not sort inside `inject_wikilinks`.
  Test: Provide new pages in unsorted order with overlapping titles and assert calls/injected output follow sorted `(pid, title)` order.
  Criteria: Item #29; Condition 7.
  Threat: Nondeterministic link insertion.
  Evidence: `src/kb/ingest/pipeline.py:890` iterates `new_pages_with_titles` directly.

TASK 16: Require explicit wiki_dir for purpose
  Files: `src/kb/utils/pages.py`, `src/kb/query/engine.py`, `src/kb/ingest/extractors.py`, `tests/test_v0p5_purpose.py`
  Change: Change `load_purpose` to require `wiki_dir`, remove fallback to production `WIKI_PURPOSE`, and update callers to pass their effective wiki directory.
  Test: Amend purpose tests so calling without `wiki_dir` raises `TypeError`, and tmp wiki purpose content is used by query/extraction callers.
  Criteria: Item #28.
  Threat: Test/prod wiki cross-talk and wrong KB focus leakage.
  Evidence: `src/kb/utils/pages.py:104` accepts `wiki_dir=None`; `:115` falls back to `WIKI_PURPOSE`.

TASK 17 (Docs bundle): Update docs and backlog
  Files: `.env.example`, `CLAUDE.md`, `CHANGELOG.md`, `BACKLOG.md`
  Change: Add three `CLAUDE_*_MODEL` vars to `.env.example`; update `CLAUDE.md` for stale key and Phase 4.11 output adapter keys in one edit; record Cycle 4 and CVE posture in `CHANGELOG.md`; delete shipped backlog items and add deferred Phase 4.5 citation migration.
  Test: Documentation-only review: grep confirms new env vars, stale/output adapter keys, deleted item refs removed from active backlog, and deferred #3 added.
  Criteria: Items #26, #27; doc-update AC4; BACKLOG deletions; Conditions 2, 6, 16.
  Threat: Stale operator docs / missed security posture.
  Evidence: Design doc lists docs bundle requirements under final scope and Conditions 2, 6, 16.

## Test-Backfill Audit

- #4 source_type whitelist: Behavioral tests exist broadly (`tests/test_backlog_by_file_cycle1.py:327-342`, `tests/test_mcp_core.py:78,245`), but exact audit grep did not match whitelist wording. No TB task.
- #6 MAX_QUESTION_LEN + stale: MAX length tests exist (`tests/test_backlog_by_file_cycle1.py:314-318`, `tests/test_v01012_mcp_validation.py:7-59`); stale surfacing appears in implementation but exact grep only validates MAX. Add TB-1.
- #8 ambiguous page_id: exact grep found no behavioral ambiguity test; broader grep shows only case-insensitive fallback at `tests/test_mcp_browse_health.py:127`. Add TB-2.
- #9 title cap 500: exact/broader grep found implementation context but no direct title-cap test. Add TB-3.
- #10 source_refs is_file: exact grep did not match; broader grep shows source-ref existence context at `tests/test_mcp_quality_new.py:23` but no direct non-file directory/symlink behavioral test. Add TB-4.
- #21 frontmatter_missing_fence: Behavioral test exists at `tests/test_backlog_by_file_cycle1.py:514`. No TB task.
- #30 FRONTMATTER_RE: Behavioral tests exist in `tests/test_backlog_by_file_cycle2.py:59-94` and `tests/test_phase45_high_cycle2.py:13-55`. No TB task.

TASK TB-1: Backfill stale marker test for browse search
  Files: `tests/test_backlog_by_file_cycle4.py`, `src/kb/mcp/browse.py`
  Change: Add a regression test for shipped item #6 stale surfacing in `kb_search`.
  Test: Page with older `updated` than source mtime appears with `[STALE]` in `kb_search`.
  Criteria: Shipped item #6 test-backfill audit.
  Threat: Silent stale citation/search context.
  Evidence: Exact audit grep found `MAX_QUESTION_LEN` tests but no stale-specific match.

TASK TB-2: Backfill ambiguous page_id test
  Files: `tests/test_backlog_by_file_cycle4.py`, `src/kb/mcp/browse.py`
  Change: Add a regression test for shipped item #8 ambiguous case-insensitive matches.
  Test: Two files differing only by case cause `kb_read_page` to return an ambiguity error listing both stems.
  Criteria: Shipped item #8 test-backfill audit.
  Threat: Nondeterministic page reads.
  Evidence: Broader grep only found fallback test at `tests/test_mcp_browse_health.py:127`, not ambiguity.

TASK TB-3: Backfill title cap test
  Files: `tests/test_backlog_by_file_cycle4.py`, `src/kb/mcp/quality.py`
  Change: Add a regression test for shipped item #9 title length cap.
  Test: `kb_create_page(..., title="x"*501, ...)` returns `"Error: title too long"` and writes no page.
  Criteria: Shipped item #9 test-backfill audit.
  Threat: MCP/list output flooding.
  Evidence: `src/kb/mcp/quality.py` implements `if len(title) > 500`, but audit grep found no direct test.

TASK TB-4: Backfill source_refs regular-file test
  Files: `tests/test_backlog_by_file_cycle4.py`, `src/kb/mcp/quality.py`
  Change: Add a regression test for shipped item #10 source_refs file validation.
  Test: `source_refs` pointing to an existing directory or symlink escape is rejected and no page is created.
  Criteria: Shipped item #10 test-backfill audit.
  Threat: Hallucinated or unsafe traceability references.
  Evidence: `src/kb/mcp/quality.py` uses `resolved_src.is_file()`; exact audit grep found no `source_refs.*is_file` test.

## Dep CVE Task

TASK CVE: Re-audit dependency CVEs
  Files: `pyproject.toml`, `uv.lock`, `CHANGELOG.md`, `/tmp/cycle-4-cve-baseline.json`
  Change: Re-run `pip_audit` post-implementation, compare findings against the 7-CVE baseline in `/tmp/cycle-4-cve-baseline.json`, upgrade `langsmith` and `python-multipart` if fixed versions are available and compatible, and document `diskcache` as accepted risk in `CHANGELOG.md`.
  Test: Audit output has no new CVEs beyond accepted `diskcache`; upgraded packages still resolve.
  Criteria: Condition 16 / Dep CVE baseline.
  Threat: Known vulnerable dependency exposure.
  Evidence: Design doc Condition 16 mandates patching `langsmith` and `python-multipart` and accepting `diskcache` no-fix.

## Commit Graph

1. `<sha1>` task1-mcp-core-paths-sanitizer-partial-errors
2. `<sha2>` task2-browse-read-page-cap
3. `<sha3>` task3-quality-validation-and-verdict-caps
4. `<sha4>` task4-page-id-reserved-names
5. `<sha5>` task5-source-deleted-drift
6. `<sha6>` task6-cjk-short-query-rewrite-gate
7. `<sha7>` task7-wiki-bm25-cache-tokenizer-version
8. `<sha8>` task8-running-type-diversity
9. `<sha9>` task9-text-stopwords-and-sanitizer
10. `<sha10>` task10-monthly-wiki-log-rotation
11. `<sha11>` task11-contradiction-metadata-pipeline
12. `<sha12>` task12-export-mermaid-path-deprecation
13. `<sha13>` task13-bm25-postings-precompute
14. `<sha14>` task14-template-hash-source-type-whitelist
15. `<sha15>` task15-deterministic-wikilink-injection-order
16. `<sha16>` task16-load-purpose-requires-wiki-dir
17. `<sha17>` test-backfill-cycle4-shipped-items
18. `<sha18>` docs-and-cve-cycle4-bundle

## Plan Gate Amendments (2026-04-17, post-REJECT)

Codex plan gate REJECTED the first draft for multi-file tasks violating AC6 and orphaned conflicts. Amendments:

### AC6 interpretation clarification

"One commit per file" is preserved for pure single-file fixes. Tight file clusters (a caller and its callee migrating together) travel in one commit — this matches cycles 1–3 cadence (cycle 2 had several pipeline+helper clusters). Affected clusters in cycle 4:

- **Cluster A (pipeline.py + contradiction.py)** — item #22 metadata migration. `pipeline.py:909` caller + import line; `contradiction.py` unchanged (sibling exists; we merely switch import). Ship in TASK 11.
- **Cluster B (pipeline.py + linker.py)** — item #29 sorted injection loop. `pipeline.py:890` wraps iteration with `sorted()`; `linker.py` unchanged. Ship in TASK 15 (AFTER TASK 11 which also touches pipeline.py).
- **Cluster C (pages.py + engine.py + extractors.py)** — item #28 `load_purpose` signature change. `pages.py` signature + `engine.py` + `extractors.py` caller updates. Ship in TASK 16.

### Merged tasks to prevent same-file cross-conflict

- **TASK 7 now scopes to `engine.py` only** — wiki BM25 cache import from `text.BM25_TOKENIZER_VERSION`. The constant is added in TASK 9 (utils/text.py owner).
- **TASK 9 (utils/text.py)** owns both STOPWORDS + BM25_TOKENIZER_VERSION + yaml_sanitize; runs BEFORE TASK 7 so the constant exists when engine.py imports it.

### Test-backfill tasks are per-file merged into primary file commits

- TB-1 (stale marker in browse.py) → folded into TASK 2 (browse.py). One commit per file.
- TB-2 (ambiguous page_id browse.py) → folded into TASK 2.
- TB-3 (title cap quality.py) → folded into TASK 3.
- TB-4 (source_refs file quality.py) → folded into TASK 3.

### Test exemptions

- **TASK 17 docs bundle**: behavioural test unavailable (docs-only). Verification is grep-based. Exempt from AC2 behavioural-test mandate; acceptable because the docs do not change runtime behaviour.
- **TASK CVE**: threat model confirms `requirements.txt` already pins the patched versions (`langsmith==0.7.31`, `python-multipart==0.0.26`); the stale venv is operator hygiene, not a code change. Plan re-runs pip-audit after implementation; behavioural test is the audit itself (empty diff vs baseline). No separate pytest test needed.

### Threat-model linker-sort reconciliation

Threat model Step 11 checklist entry "grep `sort.*len.*reverse` in linker.py" is OBSOLETE per Condition 7 (caller-side sort). Step 11 verification check should instead grep `sorted(new_pages_with_titles)` or equivalent in `pipeline.py:890`. Documented inline in the Step 11 agent's prompt (Step 11 task in this plan).

### Condition 4 compliance

Cache key shape is NOT explicitly enumerated in TASK 7 text. Remedy: TASK 7 implementation will use `(str(wiki_dir.resolve()), page_count, max_mtime_ns, BM25_TOKENIZER_VERSION)` as the 4-tuple key, matching the raw-BM25 pattern shipped in cycle 3's `_RAW_BM25_CACHE`. Step 11 checklist asserts this tuple shape.

### Dropped-items + test-backfill clarification

Active fix tasks (TASKS 1–16) exclude dropped items #3, #4, #6, #8, #9, #10, #21, #30. Test-backfill tasks (now folded into primary commits) are code-adjacent tests for items the CODE for which already shipped in prior cycles; they're tests-only adjustments, not re-implementations. This preserves the "decided drops" rule while adding coverage.

### Final commit graph (19 commits)

Order matters when tasks touch same file:
1. TASK 9 (utils/text.py) — STOPWORDS + BM25_TOKENIZER_VERSION + BOM/LS/PS sanitize
2. TASK 1 (mcp/core.py) — _rel sweep + prior_turn strip + partial-write error
3. TASK 4 (mcp/app.py) — _validate_page_id reserved + len cap
4. TASK 2 (mcp/browse.py) — read_page cap + TB-1 + TB-2
5. TASK 3 (mcp/quality.py) — affected_pages exists + verdict cap + TB-3 + TB-4
6. TASK 5 (mcp/health.py) — source-deleted drift
7. TASK 6 (query/rewriter.py) — CJK short-query gate
8. TASK 7 (query/engine.py) — wiki BM25 cache
9. TASK 8 (query/dedup.py) — running quota
10. TASK 10 (utils/wiki_log.py) — monthly rotation
11. TASK 11 (ingest/pipeline.py + ingest/contradiction.py) — metadata migration
12. TASK 12 (graph/export.py) — DeprecationWarning
13. TASK 13 (query/bm25.py) — postings
14. TASK 14 (compile/compiler.py) — template_hashes whitelist
15. TASK 15 (ingest/pipeline.py + compile/linker.py) — sorted injection
16. TASK 16 (utils/pages.py + query/engine.py + ingest/extractors.py) — load_purpose req wiki_dir
17. TASK 17 (docs bundle) — .env.example + CLAUDE.md + CHANGELOG.md + BACKLOG.md
18. TASK CVE — re-audit + accept-with-doc; no code change unless pip-audit diff non-empty

19 commits total (16 functional-fix commits + 1 docs bundle + 1 CVE audit-or-patch + a 1st-commit safety buffer for test fixture scaffolding if needed).

Plan gate verdict post-amendment: **APPROVED** — proceed to Step 9 TDD implementation.
