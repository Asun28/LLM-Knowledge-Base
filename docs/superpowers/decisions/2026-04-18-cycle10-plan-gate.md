## Verdict
PLAN-AMENDS-DESIGN

## Coverage matrix
| AC | TASK | Status |
|---|---:|:---:|
| AC0 | TASK 1 | ✓ |
| AC1 | TASK 3 | ✓ |
| AC1b | TASK 3 | ✓ |
| AC1s | TASK 2 | ✓ |
| AC2 | TASK 4 | ✓ |
| AC3 | TASK 4 | ✓ |
| AC4 | TASK 5 | ✓ |
| AC5 | TASK 5 | ✓ |
| AC6 | TASK 5 | ✓ |
| AC7 | TASK 6 | ✓ |
| AC8 | TASK 6 | ✓ |
| AC9 | TASK 7 | ✓ |
| AC10 | TASK 8 | ✓ |
| AC11 | TASK 8 | ✓ |
| AC12 | TASK 9 | ✓ |
| AC13 | TASK 9 | ✗ |
| AC14 | TASK 8 | ✗ |
| AC15 | TASK 1 | ✓ |
| AC16 | TASK 4 | ✓ |
| AC17 | TASK 5 | ✓ |
| AC18 | TASK 5 | ✓ |
| AC19 | TASK 5 | ✓ |
| AC20 | TASK 5 | ✓ |
| AC21 | TASK 4 | ✓ |
| AC22 | TASK 6 | ✓ |
| AC23 | TASK 6 | ✓ |
| AC24 | TASK 8 | ✓ |
| AC24b | TASK 8 | ✓ |
| AC25 | TASK 8 | ✓ |
| AC26 | TASK 9 | ✓ |
| AC27 | TASK 9 | ✓ |
| AC28 | TASK 10 | ✓ |
| AC28.5 | TASK 7 | ✗ |
| AC28a | TASK 7 | ✓ |

## Threat coverage
| Threat | TASK(s) / disposition |
|---|---|
| T1 | TASK 2, TASK 3 |
| T2 | TASK 2 |
| T3 | TASK 1, TASK 4, TASK 5 |
| T4 | TASK 1, TASK 4, TASK 5 |
| T5 | TASK 8 |
| T6 | TASK 8 |
| T7 | ✗ not referenced and not explicitly out-of-scope |
| T8 | ✗ not referenced and not explicitly out-of-scope |
| T9 | TASK 9 |
| T10 | TASK 9 |
| T11 | ✗ not referenced and not explicitly out-of-scope |
| T12 | TASK 4 |
| T13 | TASK 8 |
| T14 | TASK 2, TASK 3 |
| T15 | TASK 7, TASK 10 |

## Blockers
- AC13 fails the cycle-9 dual-mechanism Red Flag. Design requires both a pre-validation pass before `_check_and_reserve_manifest` and defensive `_coerce_str_field` calls inside `_build_summary_content`; TASK 9's TDD-red lines only assert pre-reservation effects (`raises`, empty dirs, `source_ref not in manifest`) and do not separately pin the defensive double-check.
- AC14 is assigned to TASK 8, but TASK 8's TDD-red lines assert capture prompt and timestamp behavior only. There is no grep-able assertion for either CLAUDE.md edit required by design AC14.
- AC28.5 is not implementation-ready. The design originally names `compile/linker.py:219-220`, while the plan preamble says the real pipe substitution is in `src/kb/utils/text.py:285-298` and reached from `linker.py:242-243`. TASK 7 chooses a linker-local override, but the plan does not prove it avoids double-escaping or avoids regressing other `wikilink_display_escape` callers. That is a plan-amends-design divergence needing explicit design approval or a stronger safety note.
- Threats T7, T8, and T11 are neither task-referenced nor explicitly marked out-of-scope. The design/requirements say the wiki-log and kb_search items are stale/dropped, but Step 8 requires every CHECKLIST threat to be mapped or explicitly scoped out in the plan.
- TASK 8's TDD-red `assert "--- INPUT ---" not in prompt` is broader than the design's AC24 test strategy, which allows escaped user content to contain the legacy literal and only forbids it as a template fence. This changes test semantics beyond the design.

## Majors
- Commit-level atomicity is mostly present: the design commit shape has 4a/4b, and plan TASK 4/TASK 5 split browse and health while both accrete `tests/test_cycle10_validate_wiki_dir.py`. However, the plan does not explicitly state that this shared test file accretes across TASK 1, TASK 4, and TASK 5 and remains compilable/relevant at each commit.
- AC2/AC21 regression-pin clarity is present in the plan's Blockers/Open questions: it says `kb_read_page` ambiguity already exists at `browse.py:87-104` and TASK 4 treats AC2/AC21 as a regression pin plus possible error-text alignment. This satisfies the no-double-implement intent.
- File-grouped commits are mostly OK: 4a/4b is present via TASK 4/TASK 5. The only allowed 3-file task is design commit 7, but plan TASK 7 also spans three files (`compiler.py`, `linker.py`, `test_cycle10_linker.py`). This matches design commit 6, not the exception named in the gate question, so Step 9 should clarify whether tests count in the "3+ files" rule.
- PLAN-AMENDS-DESIGN scan: TASK 2 matches design commit 2 (`_safe_call.py` + test). TASK 7 matches the design's compile/linker/test commit by file set, but its linker-local override is based on a newly discovered `utils/text.py` implementation detail not resolved in the design. TASK 8 matches design commit 7 by file set and Q10 bundling.

## Red-flag-scan results
- Cycle-4 inspect/source primary assertion scan: PASS — AC9 is explicitly a docstring assertion allowed by design, and the plan's TDD-red lines do not use `inspect.getsource(...)` or `re.findall(...)` as primary assertions.
- Cycle-9 dual-mechanism collapse scan: FAIL — AC13's pre-validation and defensive double-check are described in implementation text but not split into two TDD-red assertions.
- Cycle-8 grep-verified function-name scan: PASS — every function name used in TDD-red/implementation lines is covered by the plan preamble or the design's grep-verified baseline (`_validate_wiki_dir`, `_safe_call`, `_sanitize_error_str`, `vector_search`, `_build_summary_content`, `_check_and_reserve_manifest`, `inject_wikilinks`, `wikilink_display_escape`, `_extract_items_via_llm`).
