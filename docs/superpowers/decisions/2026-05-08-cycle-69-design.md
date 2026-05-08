# Cycle 69 — Design (Step 5 decision gate)

**Date:** 2026-05-08
**Tier:** 2
**Inputs:** R1 Opus APPROVE-WITH-CONDITIONS + R2 DeepSeek REJECT (mixed-quality — 1 valid signal, 3 hallucinations)
**Verdict:** APPROVE-WITH-AMENDMENTS

## Analysis

This is the binding gate that consolidates R1 (Opus subagent — APPROVE-WITH-CONDITIONS, 4 MAJORs + 6 MINORs) and R2 (DeepSeek V4 Pro — REJECT, 4 MAJORs of which only 1 surfaces a real signal). I walked through each input fact-by-fact:

**R1 fact-check.** Each of M1–M4 maps to a verifiable production line:

- **M1 (AC09 vacuous):** confirmed at `src/kb/lint/trends.py:118,120` — both branches read the module-level `VERDICT_TREND_THRESHOLD` constant. Without `monkeypatch.setattr("kb.lint.trends.VERDICT_TREND_THRESHOLD", X)` and divergent thresholds, the upgrade does not exercise the production comparison line. **Promoted as A1.**
- **M2 (AC12 frontmatter divergence):** confirmed `kb.utils.markdown:46` uses shared `FRONTMATTER_RE` (line 22: `r"\A(---[ \t]*\r?\n.{0,10000}?\r?\n---[ \t]*\r?\n?)(.*)"`). An inline mutant `re.compile(r"\A\s*---")` would diverge on a CRLF page or on a page with trailing whitespace after the opening fence. **Promoted as A2 with input pin: CRLF + tab-trailing-fence pair.**
- **M3 (AC14 non-determinism):** confirmed at `src/kb/ingest/pipeline.py:207` (`block = f"\n## {safe_ref} — {date.today().isoformat()}\n"`) AND at `pipeline.py:216` (duplicate-block check uses the same `date.today()`). Snapshot test MUST monkeypatch `kb.ingest.pipeline.date` (FakeDate returning fixed `date(2026, 5, 8)`). **Promoted as A3.**
- **M4 (AC01 + T3 incomplete):** confirmed via reading `tests/test_cycle68_backlog_cleanup_lockin.py` — the existing `DELETED_ENTRIES` tuple does NOT contain substrings unique to the AC03 path-validation entry or AC04 build_graph-callers entry. **Promoted as A4.**

**R2 hallucination audit.** I re-grepped each R2 MAJOR claim against HEAD source:

- **R2-MAJOR-1 (9 build_graph callers):** `Grep "build_graph\b" src/kb/` returned 3 in-scope callers outside `graph/cache.py` + `graph/builder.py`: `query/engine.py:408`, `evolve/analyzer.py:29`, `evolve/analyzer.py:360`. ALL THREE supply `pages=` kwarg. R2's claim of "9 sites including cli.py + lint/runner.py" is hallucinated — `cli.py` calls `build_graph_jsonld` (different function with `_jsonld` suffix), and `lint/runner.py` has zero `build_graph` calls (only docstring/comment refs in `lint/semantic.py:138` + `lint/checks/orphan.py:34`). **REJECTED.**
- **R2-MAJOR-2 (AC06 escape via get_graph):** R1 N5 already classified the get_graph branch of the AST walk as defensive-dead. The in-scope modules call `build_graph` directly with `pages=`, not `get_graph`. R2 escalates a non-issue to MAJOR. **REJECTED.**
- **R2-MAJOR-3 (AC13 datetime.now):** Read `src/kb/ingest/extractors.py:276–333`. `build_extraction_prompt(content, template, purpose)` produces a deterministic f-string from `template["extract"]` + `template["name"]` + `template.get("description","")` + `wrap_purpose(purpose)` + `_escape_source_document_fences(content)`. Zero `datetime`/`os.environ`/`time` references. R2 conflated AC13 with AC14 (the latter IS time-dependent — that's R1 M3, promoted as A3). **REJECTED.**
- **R2-MAJOR-4 (AC08 BACKLOG drift):** PARTIALLY TRUE. Of R2's 7 claims, 6 are either cycle-68 self-refs (already deleted via AC02) or historical narrative in `CHANGELOG-history.md` (correct, not drift). 1 is genuinely stale: `BACKLOG.md:130–131` Phase 4.5 MEDIUM `lint/checks/duplicate_slug.py` allowlist suggestion. Verified shipped: `BACKLOG.md` cleanup-comment line 53 explicitly states *"duplicate-slug allowlist externalization (Phase 4.5 MEDIUM) → SHIPPED cycle 68 AC04"*; `src/kb/lint/checks/duplicate_slug.py:64–78` shows the wiki/_lint.yml overlay landed; `pair in DUPLICATE_SLUG_ALLOWLIST` check is live. **PROMOTED as A5 / new AC22.**

**Cross-family review value tally for May 2026 trial telemetry:** R2 surfaced 1/4 valid MAJORs (25% precision); R1 surfaced 4/4 valid MAJORs (100% precision). R2 hallucinated 3 grep claims that primary-session caught. Telemetry: cross-family review HAS marginal value (catches BACKLOG drift R1 missed) but requires primary-session fact-check gate per `feedback_r2_codex_static_analysis_value`.

**Same-class peer scan extension.** I ran `Grep "SHIPPED cycle 6" BACKLOG.md`. All hits are inside the cleanup HTML comment block (lines 36-53) — these are NOT entries to delete; they are the documentation of past deletions. The bold-marker entries `**AC03** (SHIPPED cycle 68 AC01)` / `**AC07** (SHIPPED cycle 68 AC03+AC04)` / `**AC12** (SHIPPED cycle 68 AC05+AC06+AC13)` at lines 65–67 ARE the cycle-68 self-ref markers AC02 deletes. No additional stale entries beyond AC03/AC04/AC22 were found in active list sections.

**OOS lock-in.** OOS-1 through OOS-13 from requirements.md remain unchanged. Cycle does not widen.

**Counts target sanity.** AC22 adds 1 AC (21 → 22) + 1 BACKLOG.md edit. Test delta unchanged from requirements baseline (no new test for AC22 — the pure deletion is locked-in by extending `tests/test_cycle68_backlog_cleanup_lockin.py::DELETED_ENTRIES` per A4, which already happens for AC03/AC04). Files modified: ~18 → ~19 (no new test file; same BACKLOG.md edit). Tests: 3274 → ~3290 unchanged.

**Step 14 mutation budget per R1 C7.** Binding requirement: Step 14 dispatcher (mimocoding-rescue @ mimo-v2.5-pro) MUST mutate-test all 6 C11-L1 upgrades + AC05/AC06 lock-ins + AC13/AC14 snapshot determinism + AC09 threshold-divergence pin. Confirmed binding.

## Fact-check log

| R2 MAJOR | Status | Evidence |
|---|---|---|
| 1 — 9 build_graph callers | HALLUCINATED | `Grep "build_graph\b" src/kb/`: 3 in-scope sites (query/engine:408, evolve/analyzer:29,360); ALL supply `pages=` |
| 2 — AC06 get_graph escape | OVER-ESCALATED | R1 N5 already noted defensive-dead; in-scope modules don't call get_graph |
| 3 — AC13 datetime.now | HALLUCINATED | `Grep "datetime.now\|os.environ.get" extractors.py`: zero matches; build_extraction_prompt is pure f-string |
| 4 — AC08 BACKLOG drift | PARTIALLY VALID | 1 of 7 is real: BACKLOG.md:130–131 duplicate_slug entry shipped via cycle-68 AC04 (verified at duplicate_slug.py:64–78, cleanup-comment line 53). PROMOTED as A5 / AC22. |

**Cross-family value tally:** 1 unique-promote / 4 claimed = 25% precision. Primary-session fact-check rate: 4/4 corrected. Trial implication: keep R2 cross-family on, keep primary-session gate on.

## Promoted amendments (binding for Step 7 plan + Step 9 implementation)

- **A1 (R1 M1)** — AC09 must include `monkeypatch.setattr("kb.lint.trends.VERDICT_TREND_THRESHOLD", 0.5)` and a divergent-threshold pattern. Build a verdicts JSON fixture with two periods whose pass-rate delta exceeds 0.5 with the monkeypatch but NOT the default 0.05; assert `compute_verdict_trends(path)["trend"] == "improving"` (or `"declining"`). Mutant that hardcodes the default threshold at line 118/120 must FAIL.
- **A2 (R1 M2)** — AC12 must pin a frontmatter input where shared `FRONTMATTER_RE` (`kb.utils.markdown:22`) and inline `re.compile(r"\A\s*---")` diverge. Use a CRLF page with trailing-tab on the opening fence: `"---\t\r\n" + "title: x\r\n" + "---\r\n" + body`. Shared regex matches; inline regex either matches differently (no closing fence captured) or fails to capture the body group. Lock-in via `parse_frontmatter` returning the expected `(meta, body)` tuple.
- **A3 (R1 M3)** — AC14 must monkeypatch `kb.ingest.pipeline.date` with a `FakeDate` returning a fixed `date(2026, 5, 8)`. Snapshot the contradictions block produced for two contradictory extractions; the resulting `## <safe_ref> — 2026-05-08\n- <claim>\n` block is then deterministic across runs. Pin: also assert the duplicate-block early-return path at `pipeline.py:216` does NOT re-emit the block on second invocation (the `existing.find(block) != -1` guard).
- **A4 (R1 M4)** — AC01 must extend `tests/test_cycle68_backlog_cleanup_lockin.py::DELETED_ENTRIES` with TWO new substrings BEFORE Step 09 starts the deletions:
  - AC03 lock-in substring: `'_validate_page_id` `..` substring match'` (uniquely identifies the Phase 6 LOW path-validation entry).
  - AC04 lock-in substring: `'graph/builder.py` non-lint `build_graph` callers'` (uniquely identifies the Phase 4.5 HIGH entry).
  - The first test (`test_backlog_does_not_contain_shipped_phase_4_5_high_entries`) becomes the cumulative cross-cycle lock-in for ALL deleted entries (cycle-67 + cycle-68 + cycle-69). The second test (`test_backlog_preserves_cycle68_self_reference_entries`) is INVERTED per AC01 to assert ABSENCE of the cycle-68 self-ref markers.
- **A5 (R2 surfaced; primary-session promoted)** — **NEW AC22:** Delete BACKLOG.md:130–131 Phase 4.5 MEDIUM `lint/checks/duplicate_slug.py` `check_duplicate_slugs` allowlist entry. Verified shipped: cycle-68 AC04 (`wiki/_lint.yml` lazy YAML loader + `DUPLICATE_SLUG_ALLOWLIST` overlay live at `src/kb/lint/checks/duplicate_slug.py:64–78`). Lock-in: extend `DELETED_ENTRIES` with substring `'lint/checks/duplicate_slug.py` `check_duplicate_slugs`'`.
- **A6 (R1 N1)** — AC05 parametrize matrix should pass `wiki_dir=tmp_path` (cycle-65 AC9 pattern) for environment-independence. Test calls `_validate_page_id(page_id, check_exists=False, wiki_dir=tmp_path / "wiki")` for every row.
- **A7 (R1 N2)** — AC07 (`kb_lint`) must also exercise the `augment=True` path. `kb.mcp.health.kb_lint` has 2 `logger.error` sites (line 87 + line 129); the augment code path at line 117–130 is independently observable. Plan: parametrize over `augment ∈ {False, True}`; spy on `kb.lint.runner.run_all_checks` AND `kb.lint.augment.orchestrator.run_augment`.
- **A8 (R1 N3)** — AC08 brainstorm names wrong symbol. `kb_evolve` (`mcp/health.py:136`) calls `generate_evolution_report` (line 150), NOT `analyze_evolution`. Spy target MUST be `kb.evolve.analyzer.generate_evolution_report` (verified at `analyzer.py:342`). The `evolve/analyzer.py:29,360` `build_graph` calls are inside DIFFERENT functions (e.g., `analyze_evolution`) that `kb_evolve` does not invoke.
- **A9 (R1 N4)** — AC15 `_render_sources` snapshot — pin inputs short enough that `_truncate_source` doesn't fire OR pin `kb.config.QUERY_CONTEXT_MAX_CHARS` via monkeypatch. Plan: use 3 sources with body lengths < 100 chars each (well under any reasonable truncation threshold) AND assert in the negative-control that lowering `QUERY_CONTEXT_MAX_CHARS` via monkeypatch DOES change the snapshot (catches a regression that pins truncation off).
- **A10 (R1 N6)** — AC06 brainstorm Q2 mutation-check description is wrong. The synthetic mutation MUST be: add a bare `build_graph(wiki_dir)` call (no `pages=` kwarg) to `query/engine.py` near the existing line 408 site. The AST guard MUST FAIL on this mutation. (Renaming `pages=` to `_pages=` is NOT the right mutation — it tests AST keyword detection but a real regression would be a fresh bare call.)

## Rejected R2 MAJORs (cross-family hallucinations)

- **R2-MAJOR-1 (AC04 9 callers)** — REJECTED. Primary-session grep: 3 in-scope callers, all supply `pages=`. R2 hallucinated cli.py + lint/runner.py callers that don't exist (cli.py calls `build_graph_jsonld`, lint/runner.py has zero calls). Promote-to-amendment: NONE. Cycle-69 AC04 deletion is sound as-is.
- **R2-MAJOR-2 (AC06 escape)** — REJECTED. R1 N5 already noted: in-scope modules (query/engine.py + evolve/analyzer.py) do not call `get_graph` directly; the AST walk's `Attribute(...,attr="get_graph")` branch is defensive-dead. Not a real escape vector.
- **R2-MAJOR-3 (AC13 datetime.now)** — REJECTED. `build_extraction_prompt` is genuinely deterministic — pure f-string from inputs. Zero datetime/env references at extractors.py:276–333. R2 conflated AC13 (extraction prompt) with AC14 (contradictions block) — the ACTUAL non-determinism is in AC14 path (`pipeline.py:207,216`), promoted as A3. **No defensive monkeypatch needed for AC13** — the test pins inputs, the function is deterministic, and adding a defensive monkeypatch would dilute the snapshot's signal-to-noise ratio.

## Final AC list (cycle 69)

### Group A — BACKLOG cleanup + cycle-68 lock-in retirement (4 ACs)

- **AC01.** Revise `tests/test_cycle68_backlog_cleanup_lockin.py::test_backlog_preserves_cycle68_self_reference_entries` to assert ABSENCE of cycle-68 self-ref entries (lock-in inversion). The first test (`test_backlog_does_not_contain_shipped_phase_4_5_high_entries`) is preserved AND extended per A4 with substrings for the AC03 + AC04 deletions and per A5 for AC22.
- **AC02.** Delete BACKLOG.md cycle-68 carry-over section + AC03/AC07/AC12 markers (the entire `### CYCLE 68 carry-over` block at lines 57-67).
- **AC03.** Delete stale Phase 6 LOW `mcp/app.py:254 _validate_page_id` `..` substring entry at lines 92-93 (verified-shipped at line 291 — segment-aware).
- **AC04.** Delete stale Phase 4.5 HIGH `graph/builder.py` non-lint callers entry at lines 110-111 (verified shipped via cycle-68 AC07/AC08a/AC08b; remaining 2 sites are intentional FW-7 pages-supplying bypasses).

### Group B — Lock-in regression tests (2 ACs)

- **AC05.** New `tests/test_cycle69_app_segment_aware_lockin.py` — **behavioural** lock-in (NOT inspect.getsource): `pytest.mark.parametrize` over a 5-row matrix. Per A6: pass `wiki_dir=tmp_path / "wiki"` for environment-independence.

  | Input | check_exists | Expected | Why |
  |---|---|---|---|
  | `"notes..draft"` | `False` | `None` | Legitimate filename containing `..` substring (NOT a segment) |
  | `"foo/../bar"` | `False` | error containing `parent-directory segment` | Real `..` segment must be rejected |
  | `"foo/..bar"` | `False` | `None` | `..bar` is NOT a `..` segment (substring trap) |
  | `"../foo"` | `False` | error containing `parent-directory segment` | Leading `..` segment |
  | `"foo\\..\\bar"` | `False` | error | Windows-separator handling (`replace("\\", "/")`) |

  Mutation budget (Step 14): rows 1, 3, 5 force divergence between segment-aware (current) and substring (regression). Sufficient.

- **AC06.** New `tests/test_cycle69_graph_builder_intentional_bypasses.py` — AST guard. Per A10: parse `query/engine.py` + `evolve/analyzer.py`, walk all `Call(func=Name("build_graph"))` nodes, assert each call site supplies `pages=` (as a keyword arg). The `Attribute(...,attr="get_graph")` branch retained as defensive-dead. Mutation budget (Step 14): add a bare `build_graph(wiki_dir)` call (no `pages=`) near `query/engine.py:408` → AC06 must FAIL. Restore source.

### Group C — C11-L1 inspect.getsource batch upgrade (6 ACs)

- **AC07.** `tests/test_lint_query_fixes_v092.py:279` — currently inspects `kb_lint` source for a string. Upgrade: monkeypatch `kb.lint.runner.run_all_checks` (spy returning a fixed report) AND per A7 also `kb.lint.augment.orchestrator.run_augment` for the augment path; invoke `kb_lint(wiki_dir=tmp_kb_env)` with `augment ∈ {False, True}` parametrize; assert spies called and behavioural output matches.
- **AC08.** `tests/test_lint_query_fixes_v092.py:286` — same pattern for `kb_evolve`. Per A8: spy target is `kb.evolve.analyzer.generate_evolution_report` (verified at `analyzer.py:342`), NOT `analyze_evolution`. Invoke via `kb_evolve(wiki_dir=tmp_kb_env)`; assert spy called once and that the resulting MCP response embeds `format_evolution_report`'s output.
- **AC09.** `tests/test_v0911_phase392.py:245` — currently inspects `trends_module` source. Per A1: import `compute_verdict_trends`; build a 2-period verdicts JSON fixture; monkeypatch `kb.lint.trends.VERDICT_TREND_THRESHOLD` to a divergent value (e.g., 0.5 vs the default 0.05); assert the trend label flips between `"stable"` and `"improving"`/`"declining"` based on the threshold. Mutant that hardcodes the default in trends.py:118/120 must FAIL.
- **AC10.** `tests/test_v0915_task01.py:320` — currently asserts `"WIKI_SUBDIRS" in inspect.getsource(builder)`. Upgrade: import `kb.config.WIKI_SUBDIRS` AND `kb.graph.builder.build_graph`; build a tmp wiki with one file inside a `WIKI_SUBDIRS` subdir AND one file outside; call `build_graph(wiki_dir=tmp_path)`; assert only the inside file appears as a node in the resulting `nx.DiGraph`. Mutant that comments out the `WIKI_SUBDIRS` import must FAIL.
- **AC11.** `tests/test_v0915_task01.py:331` — analyzer inspect.getsource. Upgrade: invoke `analyze_evolution` (verified `evolve/analyzer.py` exposes it at line 17 import via `from kb.graph.builder import build_graph, graph_stats`) with a controlled wiki fixture and assert behavioural output for the relevant code path.
- **AC12.** `tests/test_v0915_task08.py:363` — analyzer inspect.getsource. Per A2: pin frontmatter divergence input. Upgrade: import `kb.utils.markdown.parse_frontmatter`; pass a CRLF + tab-trailing-fence input where shared `FRONTMATTER_RE` matches but inline `\A\s*---` regex would NOT capture the closing fence + body correctly; assert returned `(meta, body)` tuple. Mutant replacing shared regex with inline `re.compile(r"\A\s*---")` must FAIL.

### Group D — Snapshot subjects (cycle-64 deferred follow-up, 3 ACs)

- **AC13.** `test_build_extraction_prompt_snapshot` — pins `kb.ingest.extractors.build_extraction_prompt(content, template, purpose)` for a fixed (content, template, purpose) triple. Function verified deterministic (extractors.py:276–333; zero datetime/env refs). NO defensive monkeypatch. Negative-control: mutate `purpose` from `"extract_entities"` to `"extract_concepts"`; assert rendered prompt's `KB FOCUS` clause changes.
- **AC14.** `test_contradictions_append_snapshot` — pins the contradictions block produced by `_persist_contradictions` (`ingest/pipeline.py:185-221`) for a fixed pair of contradictory extractions. Per A3: monkeypatch `kb.ingest.pipeline.date` with a `FakeDate` returning `date(2026, 5, 8)` so the `## {safe_ref} — {date.today().isoformat()}\n` header (line 207) is deterministic. Negative-control: change second extraction's claim text; assert snapshot differs.
- **AC15.** `test_lint_semantic_render_sources_snapshot` — pins `kb.lint.semantic._render_sources(sources, lines)` for a fixed inputs. Per A9: use 3 sources < 100 chars each (well under truncation threshold). Negative-control 1: change a source's `confidence` from `stated` to `inferred`; assert `lines` differs. Negative-control 2: monkeypatch `kb.config.QUERY_CONTEXT_MAX_CHARS` to a small value (e.g., 50); assert `lines` differs (catches a regression that pins truncation off).

### Group E — Freeze-and-fold (4 small versioned tests, 4 ACs)

- **AC16.** Fold `tests/test_v0917_rewriter.py` (4 tests, 30 lines) → `tests/test_query.py` as bare functions.
- **AC17.** Fold `tests/test_v0917_raw_fallback.py` (3 tests, 32 lines) → `tests/test_query.py` as a `TestSearchRawSources` class.
- **AC18.** Fold `tests/test_v01002_consolidated_constants.py` (~44 lines) → `tests/test_config.py` (extends `TestConfigConstants` class).
- **AC19.** Fold `tests/test_v0917_hybrid.py` (47 lines) → `tests/test_query.py` as a `TestHybridQuery` class.

### Group F — Documentation (2 ACs)

- **AC20.** CHANGELOG.md / CHANGELOG-history.md / BACKLOG.md / CLAUDE.md sync per CLAUDE.md doc-checklist. Per `feedback_deepseek_doc_disambiguation` memory: pre-emptively disambiguate in-project modules vs PyPI libraries when DeepSeek dispatches the doc-update. Cycle-69 ZERO `src/kb/` migrations — Step 17 prompt MUST forbid "migrated to LIB" wording.
- **AC21.** docs/superpowers/decisions/2026-05-08-cycle-69-* artifacts: requirements (this file) + threat-model + brainstorm + design-eval-R1-opus + design-eval-R2-deepseek + design (this gate) + plan + plan-gate + step24-self-review.

### Group G — NEW: Additional BACKLOG cleanup (1 AC; promoted from R2 surfacing)

- **AC22.** Delete BACKLOG.md:130–131 Phase 4.5 MEDIUM `lint/checks/duplicate_slug.py` `check_duplicate_slugs` allowlist entry. Verified shipped: cycle-68 AC04 (cleanup-comment line 53; live overlay at `src/kb/lint/checks/duplicate_slug.py:64–78`). Lock-in: extend `tests/test_cycle68_backlog_cleanup_lockin.py::DELETED_ENTRIES` per A5 with substring `'lint/checks/duplicate_slug.py` `check_duplicate_slugs`'`. Per A4, AC22 substring is added to the SAME `DELETED_ENTRIES` tuple as AC03 + AC04 substrings (cumulative cross-cycle lock-in).

## Step 14 binding mutation budget

For each of the following, Step 14 dispatcher (mimocoding-rescue @ mimo-v2.5-pro) MUST run the mutation, observe test FAILs, restore source:

- **AC05 row 1/3/5:** revert `mcp/app.py:291` to substring form (`if ".." in page_id:`) → AC05 must FAIL on rows 1 (notes..draft → falsely rejected), 3 (foo/..bar → falsely rejected), 5 (foo\\..\\bar → behaviour change).
- **AC06:** add bare `build_graph(wiki_dir)` call (no `pages=`) near `query/engine.py:408` → AC06 must FAIL.
- **AC07 (default):** change `logger.error` → `logger.exception` at `mcp/health.py:87` → AC07 spy assertion must FAIL (or spy on non-error path, depending on assertion shape).
- **AC07 (augment):** change `logger.error` → `logger.exception` at `mcp/health.py:129` → AC07 augment-parametrize must FAIL.
- **AC08:** change `logger.error` → `logger.exception` at `mcp/health.py:153` → AC08 must FAIL.
- **AC09:** hardcode 0.05 (default) at `trends.py:118` (drop monkeypatch sensitivity) → AC09 must FAIL — the test sets the threshold to 0.5 via monkeypatch and exercises a delta in the [0.05, 0.5] range so the trend label MUST change between defaults and the monkeypatched value.
- **AC10/AC11:** comment out `WIKI_SUBDIRS` import in `kb/graph/builder.py` (or relevant analyzer) → must FAIL with `NameError` AND the behavioural assertion (only-inside files become nodes) must FAIL.
- **AC12:** replace shared `FRONTMATTER_RE` with inline `re.compile(r"\A\s*---")` in `kb.utils.markdown.parse_frontmatter` → AC12 (CRLF + tab-trailing-fence) must FAIL.
- **AC13 (anti-confounder check):** inject `f"// generated at {datetime.now().isoformat()}"` into `build_extraction_prompt` output → snapshot MUST CHANGE on second run (verifies the test's positive-control captures determinism). Restore source.
- **AC14:** drop the `FakeDate` monkeypatch — snapshot test must FAIL on second day (the date-stamp shifts day-over-day).
- **AC15:** monkeypatch `kb.config.QUERY_CONTEXT_MAX_CHARS` to a small value (e.g., 50) so `_truncate_source` fires — snapshot MUST CHANGE.
- **AC22 lock-in:** add the duplicate_slug entry back to BACKLOG.md → `tests/test_cycle68_backlog_cleanup_lockin.py::test_backlog_does_not_contain_shipped_phase_4_5_high_entries` must FAIL.

## OOS lock-in

OOS-1 through OOS-13 from requirements.md remain unchanged:

- **OOS-1:** `tests/test_compile.py:211,221` `inspect.getsource(compiler)` — intentional lint-shipped-pattern, NOT C11-L1.
- **OOS-2:** `tests/test_cycle65_mcp_error_boundary.py:107` and `tests/test_cycle67_sqlite_vec_error_sanitization.py:121` `inspect.getsource` — recent anchors with current behavioural coverage; cycle-69 does not re-litigate.
- **OOS-3:** `compile/compiler.py` naming inversion — architecture refactor.
- **OOS-4:** `ingest/pipeline.py` state-store fan-out + per-source rollback.
- **OOS-5:** All 25 sync `def` MCP tools async refactor.
- **OOS-6:** `compile_wiki` two-phase pipeline.
- **OOS-7:** `IndexWriter` consolidation (defer until 4th caller).
- **OOS-8:** `KB_DISABLE_VECTORS=1` runtime kill-switch — already SHIPPED cycle 67 AC06.
- **OOS-9:** `KB_STRICT_PUBLISH=1` — already SHIPPED cycle 67 AC04.
- **OOS-10:** Phase 5 community proposals.
- **OOS-11:** Phase 6/7/8 candidates.
- **OOS-12:** Snapshot subjects beyond AC13–AC15 (`_build_summary_content`, `kb publish --format graph` JSON-LD, `auto_publish_after_compile` body) — deferred cycle-70+.
- **OOS-13:** windows-latest CI matrix re-enable, GHA-Windows multiprocessing spawn, TestWriteItemFiles POSIX off-by-one — N/A prerequisites unavailable; bumped cycle-70+.

## Counts target

- **ACs:** 22 (was 21; +1 for AC22 new). R3 PR review still fires per cycle-16 L4 (≥15 ACs + new lock-in test surface).
- **Files modified:** ~19 (was ~18; +1 BACKLOG.md edit folded into existing AC02/AC03/AC04 BACKLOG.md edit so net file delta is 0; AC22's lock-in extension lands in existing `tests/test_cycle68_backlog_cleanup_lockin.py` — also no new file).
- **Tests:** 3274 → ~3290 (+~16 net: +6 lock-in including AC22 extension, +3 snapshots, +6 negative controls, +4 fold-receivers; -4 fold-source files net 0 tests).
- **src/kb/ changes:** 0 (pure hygiene cycle).
- **Step 14 mutation budget:** 12 mutations (was 10 in R1 plan; +AC13 anti-confounder + AC22 lock-in).
