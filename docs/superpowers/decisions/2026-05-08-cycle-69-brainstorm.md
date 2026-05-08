# Cycle 69 — Brainstorming

**Date:** 2026-05-08
**Step:** 03 (Opus main; Skill `superpowers:brainstorming` discipline)
**Inputs:** requirements.md (21 ACs) + threat-model.md (T1–T6 active)

This cycle is hygiene-only. Brainstorming surfaces the few non-trivial design choices: lock-in test shape (T1), C11-L1 upgrade pattern (T6), and snapshot subject framing (T4).

## Q1 — How to structure the AC05 segment-aware lock-in (T1 vacuousness risk)

**Approach A — Direct behavioural matrix.** Import `_validate_page_id` from `kb.mcp.app`; assert against a small input-output matrix:

| Input | check_exists | Expected | Why |
|---|---|---|---|
| `"notes..draft"` | `False` | `None` | Legitimate filename containing `..` substring (NOT a segment) |
| `"foo/../bar"` | `False` | error containing `parent-directory segment` | Real `..` segment must be rejected |
| `"foo/..bar"` | `False` | `None` | `..bar` is NOT a `..` segment (substring trap) |
| `"../foo"` | `False` | error containing `parent-directory segment` | Leading `..` segment |
| `"foo\\..\\bar"` | `False` | error | Windows-separator handling (`replace("\\", "/")`) |

**Pros.** Mutation-resistant — a regression to substring `".." in page_id` BLOCKS rows 1, 3, and 5 (each has `..` substring but no `..` segment). Direct, behavioural, no monkeypatch needed.
**Cons.** Five rows is verbose. Could be parametrized.

**Approach B — Property test via Hypothesis.** Generate random page_ids and assert the segment-aware contract holds (`reject_iff path.replace("\\","/").split("/")` contains `".."`).

**Pros.** Catches edge cases automatically.
**Cons.** Adds a dev dependency the project hasn't taken; cycle-69 is hygiene, not feature; out of scope for the trial budget.

**Approach C — AST-only structural lock-in.** Parse `mcp/app.py`, walk the function body of `_validate_page_id`, find the `..`-related check, assert it uses `seg == ".."` form (NOT `".." in page_id`).

**Pros.** Strongest static-analysis lock-in.
**Cons.** Source-string-read in disguise (cycle-11 L1 violation). Drops to vacuous if a clever refactor preserves substring-form intent through a different syntax.

**Decision: Approach A, parametrized.** Direct behavioural matrix using `pytest.mark.parametrize`. Five rows. Ship as `test_validate_page_id_segment_aware_not_substring` with a paired explanatory docstring referring to cycle-69 AC03 BACKLOG deletion.

## Q2 — How to structure the AC06 graph-builder intentional-bypass lock-in (T1 + R1 review surface)

**Approach A — Pure AST guard.** Parse `query/engine.py` and `evolve/analyzer.py` with `ast.parse`, walk every `Call` node whose `func` is `Name("build_graph")` OR `Attribute(...,attr="get_graph")`, assert each call site EITHER supplies `pages=` (as a keyword arg) OR is one of a small allow-list of explicit lint-pass entries (cycle-68 AC07 migrated `analyzer.py:127` — already gone).

**Pros.** Catches new build_graph callers added in any future cycle. Mutation-resistant.
**Cons.** AST walks are brittle if the codebase introduces a wrapper function; would need an OOS allow-list for wrappers.

**Approach B — Behavioural spy.** Spy on `kb.graph.cache.get_graph` and `kb.graph.builder.build_graph`; invoke `query_wiki(...)` and `analyze_evolution(...)` end-to-end; assert the spy on `get_graph` is NOT called from those code paths and the spy on `build_graph` IS called with `pages=` supplied.

**Pros.** Tests RUNTIME behaviour, not source structure.
**Cons.** Requires a full e2e harness (wiki fixtures, vector DB, etc.); over-spend for a hygiene cycle.

**Decision: Approach A.** AST guard with explicit allow-list for any `pages=`-supplying call. Lock-in test in `tests/test_cycle69_graph_builder_intentional_bypasses.py`. Mutation check: rename a `pages=` kwarg to `_pages=` in the AST walk; test FAILs (synthetic mutation).

## Q3 — C11-L1 batch upgrade pattern (T6 — broader monkeypatch surface)

**Common shape across AC07–AC12:**

For each `inspect.getsource(F) + "X" in src` site:
1. Identify what `"X"` actually checks (`grep -n "<X>" src/kb/<module>.py` to find the production line).
2. Identify the production CALL PATH (which entry point calls F? what input would route through line X?).
3. Replace the source-grep with: `monkeypatch.setattr("<production_module>.<helper>", spy)` + invoke entry → assert `spy.call_count > 0` AND/OR assert behavioural output matches expected.

**Per-site sketch:**

- **AC07 (test_lint_query_fixes_v092.py:279 — kb_lint inspect.getsource):** Read the test to understand intent. Likely checking that `kb_lint` calls `run_all_checks`. Upgrade: spy on `kb.lint.runner.run_all_checks`, invoke `kb_lint(wiki_dir=tmp_path / "wiki")` with a minimal fixture, assert spy called once.
- **AC08 (test_lint_query_fixes_v092.py:286 — kb_evolve):** spy on `kb.evolve.analyzer.analyze_evolution`, invoke `kb_evolve(...)`, assert spy called.
- **AC09 (test_v0911_phase392.py:245 — trends_module):** likely checking a function existence in `kb.feedback.trends` or similar. Upgrade: import that function; assert it returns a known shape for a known input.
- **AC10 (test_v0915_task01.py:320 — `WIKI_SUBDIRS` in builder source):** the test asserts the builder *uses* WIKI_SUBDIRS. Upgrade: import `WIKI_SUBDIRS`; build a tmp wiki with a file inside AND outside the subdirs; call `build_graph`; assert only the inside file appears as a node.
- **AC11 / AC12 (analyzer source):** identify the asserted symbol (e.g., a function or constant) and write a minimal behavioural assertion.

**Decision:** keep all 6 upgrades in their existing files (no new test file). The "extract a helper" cycle-11 L1 exhortation applies when the test CAN'T directly invoke the changed line — for these 6, behavioural spy + entry invocation IS direct invocation.

## Q4 — Snapshot subject framing (T4 — leak risk)

For each AC13–AC15 snapshot, the inputs are constructed inline in the test file with hardcoded strings (no `os.environ`, no `Path.home`, no live wiki paths beyond `tmp_path`). Each snapshot includes a paired non-vacuous negative-control per cycle-67 AC09: mutate one input bit, assert the captured snapshot DIFFERS from the baseline (NOT just `assert "X" in snapshot` — that's vacuous).

**AC13 — `build_extraction_prompt` snapshot:** input is a fixed `(content, template, purpose)` triple. Output is the rendered prompt string. Negative-control: mutate `purpose` from `"extract_entities"` to `"extract_concepts"`; assert the rendered prompt's `purpose` clause changes.

**AC14 — contradictions append:** the contradictions append code path lives in `ingest/pipeline.py`. Need to identify the public entry. Plan: spike to find the function; if it's `ingest_source`, set up two contradictory extractions and snapshot the resulting `wiki/contradictions.md` body. Negative-control: change the second extraction's claim text; assert snapshot differs.

**AC15 — `_render_sources` snapshot:** in `kb.lint.semantic`. Pin the output for a fixed `sources: list[dict]` and `lines: list[str]` pair. Negative-control: change a source's `confidence` from `stated` to `inferred`; assert `lines` differs.

**Decision:** all three subjects are tractable. Inline inputs only; no environment leakage. Pair each with negative-control per cycle-67 AC09.

## Q5 — Fold-receiver shape decisions (C40-L5 host-shape)

**Receiver `tests/test_query.py`:**
- AC16 (test_v0917_rewriter.py — 4 tests, 30 lines) → bare-function (test_query.py has both shapes; 4-test set fits bare).
- AC17 (test_v0917_raw_fallback.py — 3 tests, 32 lines) → `TestSearchRawSources` class (cohesion around `search_raw_sources`).
- AC19 (test_v0917_hybrid.py — 47 lines) → `TestHybridQuery` class.

**Receiver `tests/test_config.py`:**
- AC18 (test_v01002_consolidated_constants.py — 44 lines) → extends `TestConfigConstants` class (created cycle-47).

Per Step-5 host-shape rule: each receiver's existing shape is preserved. No source-file's tests are renamed unless they collide with an existing receiver-side method name.

## Out of scope for this brainstorm (deferred to design eval if R1/R2 raises)

- Whether to also fold `test_v0917_layered_context.py` (45 lines) — currently NOT in the AC list. R2 may flag as a same-class-peer fold candidate.
- Whether to extend `test_backlog_does_not_contain_shipped_phase_4_5_high_entries::DELETED_ENTRIES` with the AC03/AC04 strings (T3 mitigation). Captured here as "yes, this is part of AC01" for the Step 7 plan.

## Decisions matrix (pre-Step-04 design eval)

| Q | Choice | Rationale |
|---|---|---|
| Q1 | Approach A (parametrized matrix) | Mutation-resistant, no extra deps, hygiene-budget-fit |
| Q2 | Approach A (AST guard) | Future-cycle-safe; behavioural e2e is over-spend |
| Q3 | spy + invoke entry pattern, in-place | Direct invocation means C11-L1's "extract helper" caveat doesn't apply |
| Q4 | inline-input snapshots + paired non-vacuous negative-controls | T4 mitigation + cycle-67 AC09 pattern |
| Q5 | host-shape preserved per fold | C40-L5 |

## Step 04 design-eval prompt anchors

These are the questions R1 (Opus subagent) and R2 (DeepSeek) MUST address:

1. **Lock-in vacuousness:** can AC05 / AC06 be reverted in production while the lock-in test still passes? (Mutation budget: revert each in production; both tests must FAIL.)
2. **C11-L1 upgrade depth:** for AC07–AC12, does the behavioural assertion exercise the production line that the original `inspect.getsource` was checking?
3. **Snapshot determinism:** for AC13–AC15, are the inputs free of environmental dependence (no `os.environ`, no `Path.home`, no live FS)?
4. **Fold completeness:** are any helpers / fixtures defined in fold sources but consumed elsewhere?
5. **BACKLOG deletion safety:** does AC02 + AC03 + AC04 leave any dangling reference (CHANGELOG, docs/reference/*, test docstrings)?
6. **Same-class peer scan:** are there other versioned-test inspect.getsource sites being missed (cycle-15 L1 / cycle-16 L1 patterns)? (`OOS-1` and `OOS-2` are addressed; R2 should sanity-check.)
