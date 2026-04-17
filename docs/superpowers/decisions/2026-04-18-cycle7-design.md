---
title: "Cycle 7 — design decision gate output"
date: 2026-04-18
type: design
feature: backlog-by-file-cycle7
---

# Cycle 7 — Design Decision Gate (Step 5) — APPROVED-WITH-AMENDMENTS

## VERDICT
Design: APPROVED

## Per-AC Final Design Amendments

| AC | Final decision |
|---|---|
| **AC12** | Widen to all `OSError`/`FileNotFoundError`-carrying sites in `mcp/core.py` (~12 of 16) via new helper `_sanitize_error_str(e, path)`; JSON-decode + LLMError sites may keep `{e}` as-is. |
| **AC13** | Add `mcp/health.py:204` (`kb_detect_drift`). Same helper. |
| **AC23** | Rename sentinel tag to `<kb_purpose>` (align AC to existing `wrap_purpose`). ADD close-sentinel escape inside `wrap_purpose` (rewrite `</kb_purpose>` → `</kb-purpose>` mirroring `_escape_source_document_fences`). Update docstring. |
| **AC27** | Widen to cover `mcp/health.py:76-77` as second silent-degradation site. Extract `_safe_call` to shared location (e.g., `kb.lint._safe_call`). |
| **AC9/10/11** | Commit order AC11 → AC10 → AC19 → AC9 → AC8. Each commit standalone-passing via optional-kwarg default. |
| **AC18** | Drop `_categories.md` from exclusion. Exclude `(index.md, _sources.md, log.md)` only. |
| **AC15** | Behavioural assert — mutate an UNRELATED source, run `find_changed_sources()` twice, assert `_template/article` key AND hash value preserved across both runs. |
| **AC3** | Populate 9 entries inside the test body; autouse reset runs post-test, not mid-test; no opt-out needed. |
| **AC19** | Grouping-only (three `_group_by_*`). Render step's disk read stays; file follow-up for render. |
| **AC2** | Keep public return type `list[list[float]]`. Push the optimization into `rebuild_vector_index` / `VectorIndex.build` which bypass `embed_texts` for the batch path and call `model.encode(texts)` directly into `sqlite_vec.serialize_float32`. |
| **AC5/AC7** | Apply `_mask_code_blocks` before regex substitution, unmask after. Mirror `compile/linker.py`. |
| **AC30** | Guard at top of `cli.py` BEFORE any `kb.config` imports. `from kb import __version__` must not trigger config transitive. |

## Dependency order for Step 7 plan

1. **AC11** — `graph/builder.py` `build_graph(pages=None)` kwarg.
2. **AC10** — `compile/linker.py` `build_backlinks(pages=None)` kwarg.
3. **AC19** — `lint/semantic.py` `build_consistency_context(pages=None)` + three `_group_by_*`.
4. **AC9** — `evolve/analyzer.py` consumer of AC10 + AC11.
5. **AC8** — `ingest/pipeline.py` `_find_affected_pages` consumer of AC10.
6. Shared helpers first (before consumers): `_sanitize_error_str` (AC12/13), `_safe_call` (AC27), `_mask_code_blocks` usage (AC5/AC7).
7. All remaining ACs batch-by-file.

## Open questions — all resolved

| # | Question | Decision | Confidence |
|---|----------|----------|------------|
| Q1 | AC12 scope | A — widen to all path-carrying sites | high |
| Q2 | AC13 add drift | A — include | high |
| Q3 | AC23 sentinel name | D — `<kb_purpose>` | high |
| Q4 | AC23 close-sentinel escape | A — escape inside wrap_purpose | high |
| Q5 | AC27 second site | B — `mcp/health.py:76-77` | medium |
| Q6 | Threading commit order | A — linear leaf-first | high |
| Q7 | AC18 `_categories.md` | A — drop | high |
| Q8 | AC15 assert form | B — behavioural round-trip | high |
| Q9 | AC3 vs AC1 conflict | B — insert-in-body suffices | high |
| Q10 | AC12/13 deep leak | A — `_sanitize_error_str` helper | high |
| Q11 | AC19 render scope | A — grouping only | medium |
| Q12 | AC2 public contract | C — preserve; push optimization into build | high |
| Q13 | AC5/AC7 code blocks | A — mask/unmask via existing helper | high |
| Q14 | AC30 guard placement | A — top of cli.py | high |

## Step 6 Context7 verification — SKIPPED

Scope contains only: `python-frontmatter` (already used in refiner.py for reads), `pyyaml` (stdlib-adjacent, widely used), `sqlite-vec` (already consumed in embeddings.py for queries), `numpy` (already a transitive via model2vec). All libraries are internally used; no new external API. Per Step 6 skip clause "pure stdlib/internal code".
