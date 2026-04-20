VERDICT: PLAN-AMENDS-DESIGN-DISMISSED

PLAN-AMENDS-DESIGN-DISMISSED: Step 7 orders TASK 1 (`src/kb/config.py`, AC3/AC14/AC15/AC16) before query/lint work even though the final design lists query/lint before config. Reason: both orderings preserve every named dependency constraint; TASK 2 and TASK 3 consume `AUTHORED_BY_BOOST` / `decay_days_for(topics=...)`, so config-first is a valid implementation ordering. No Step-5 re-run needed.

## COVERAGE TABLE

| Row | Plan coverage | Status |
|---|---|---|
| AC1 | TASK 2 `_flag_stale_results` adds decay gate alongside mtime, no-source skip, multi-source max test fixtures. | check |
| AC2 | TASK 2 `_build_query_context` uses `tier1_budget_for("summaries")`; test monkeypatches split and asserts shrink. | check |
| AC3 | TASK 1 adds `AUTHORED_BY_BOOST`; TASK 2 adds validated `_apply_authored_by_boost`; AC22/T7 tests included. | check |
| AC4 | TASK 3 changes `check_staleness(max_days: int \| None = None)` and per-source decay behavior; AC23 tests included. | check |
| AC5 | TASK 3 adds `check_status_mature_stale`; mature/seed/developing/evergreen/missing-status assertions included. | check |
| AC6 | TASK 3 adds Evidence Trail-scoped `check_authored_by_drift`; T5 false-positive tests included. | check |
| AC7 | TASK 3 wires AC5/AC6 into `run_all_checks`; integration assertion included. | check |
| AC9 | TASK 4 migrates `build_llms_txt` to `atomic_text_write`; spy assertion included. | check |
| AC10 | TASK 4 migrates `build_llms_full_txt` to `atomic_text_write`; spy assertion included. | check |
| AC11 | TASK 4 migrates `build_graph_jsonld` to atomic JSON text write; failure cleanup assertion included. | check |
| AC12 | TASK 4 adds `_publish_skip_if_unchanged` and `incremental=False` builder kwargs; skip/regenerate/freshen/index/T10c/docstring assertions included. | check |
| AC13 | TASK 5 adds `--incremental/--no-incremental`, plumbs builder kwargs after containment; default/no-incremental/containment tests included. | check |
| AC14 | TASK 1 adds casefolded read-only `SOURCE_VOLATILITY_TOPICS`; mapping/freeze/casefold tests included. | check |
| AC15 | TASK 1 adds capped, escaped, boundary-matched `volatility_multiplier_for`; length-cap/boundary/max tests included. | check |
| AC16 | TASK 1 extends `decay_days_for(..., topics=None)` with finite/positive fallback and clamp; NaN/inf/zero/negative/clamp tests included. | check |
| AC20 | TASK 2 `test_cycle15_query_decay_wiring.py` covers AC1 fixtures, including multi-source lenient max. | check |
| AC21 | TASK 2 `test_cycle15_query_tier1_wiring.py` proves helper-driven tier-1 budget. | check |
| AC22 | TASK 2 `test_cycle15_authored_by_boost.py` covers human/hybrid, llm/absent, invalid value, invalid frontmatter gate. | check |
| AC23 | TASK 3 `test_cycle15_lint_decay_wiring.py` covers per-source decay, multi-source max, override, no-source fallback. | check |
| AC24 | TASK 3 `test_cycle15_lint_status_mature.py` covers 91d/89d and status filtering. | check |
| AC25 | TASK 3 `test_cycle15_lint_authored_drift.py` covers in-scope ingest, hybrid/edit/no-trail/code-fence/CRLF/EOF cases. | check |
| AC27 | TASK 4 `test_cycle15_publish_atomic.py` covers all three atomic writes plus JSON-LD temp cleanup failure. | check |
| AC28 | TASK 4 `test_cycle15_publish_incremental.py` covers skip, regeneration, mtime freshen, index exclusion, T10c filter ordering, docstring. | check |
| AC29 | TASK 5 `test_cycle15_cli_incremental.py` covers CLI defaults, `--no-incremental`, and path containment before mkdir. | check |
| AC30 | TASK 1 `test_cycle15_config_volatility.py` covers volatility mapping, multiplier, decay topics, T1, and T2 cases. | check |
| AC32 | TASK 6 `test_cycle15_load_all_pages_fields.py` covers `authored_by`, `belief_state`, absent defaults, and `status` regression. | check |
| T1 -> AC15 | TASK 1 length cap and `re.escape`/word-boundary tests cover ReDoS/metachar risk. | check |
| T2 -> AC16 | TASK 1 NaN/inf/zero/negative/clamp tests cover decay overflow and bad multiplier risk. | check |
| T3 -> AC12 | TASK 4 docstring assertion covers single-writer/incremental TOCTOU contract. | check |
| T4 -> AC11 | TASK 4 JSON-LD failure cleanup test covers same-directory temp/atomic residue behavior. | check |
| T5 -> AC6 | TASK 3 no-trail and code-fence-above-trail tests cover Evidence Trail false positives. | check |
| T7 -> AC3 | TASK 2 invalid-frontmatter no-boost test covers ranking boost gate. | check |
| T8 -> AC13 | TASK 5 containment regression covers CLI flag bypass risk. | check |
| T10c -> docs | TASK 7 includes CHANGELOG operator note for first post-upgrade `kb publish --no-incremental`. | check |
| Exact files/changes/assertions | TASKS 1-6 list files, code changes, and concrete test assertions; TASK 7 lists docs files and required doc outcomes. | check |
| Dependency order | TASK 1 before TASK 2/3; TASK 4 before TASK 5; TASK 5 explicitly preserves cycle-14 T1 path containment. | check |
| Anti-pattern scan | Proposed tests avoid signature-only source inspection, file-text source grep, `re.findall` over source as primary assertion, vacuous conditionals, and subprocess without `PYTHONPATH`. | check |

## GAPS

- None blocking.

## RECOMMENDATIONS

- In TASK 7 execution, keep the T10c CHANGELOG note, AC8-carry BACKLOG entry, and CLAUDE stats/update bullets in the same docs commit so the mandatory Step-12 docs condition remains auditable.
- In TASK 4 execution, ensure the JSON-LD cleanup test patches the same symbol actually used by `build_graph_jsonld`; the plan names both `kb.compile.publish.atomic_text_write` spies and a lower-level failure simulation, so the final test should assert behavior rather than only the import path.
