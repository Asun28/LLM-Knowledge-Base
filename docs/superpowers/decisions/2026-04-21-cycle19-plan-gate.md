# Cycle 19 Plan Gate

## Verdict
REJECT-WITH-AMENDMENTS

The plan covers most production ACs, but three gate blockers remain: TASK 2 has the wrong live `_check_and_reserve_manifest` parameter shape in its implementation snippet, TASK 1 does not implement/verify T2's required null-byte title sanitizer, and TASK 5's AC17 scope is not grep-confirmed (the claimed 6-file intersection is false in the current repo).

## AC coverage matrix
| AC | task | test? | files confirmed | status |
|----|------|-------|-----------------|--------|
| AC1 | TASK 1 | T-1 | linker helpers exist | AMEND: add T2 null sanitizer |
| AC1b | TASK 1 | T-1b | linker.py | OK |
| AC2 | TASK 1 | T-2/T-2b | linker.py | OK |
| AC3 | TASK 1 | T-3 | linker.py | OK |
| AC4 | TASK 1 | T-4 | config.py/linker.py | OK |
| AC4b | TASK 1 | T-4b | config.py/linker.py | OK |
| AC5 | TASK 1 | T-5 | linker.py | OK |
| AC6 | TASK 1 | T-6b | pipeline.py/linker.py | OK |
| AC7 | TASK 1 | T-7 | pipeline.py/linker.py | OK |
| AC8 | TASK 3 | T-8/T-8a/T-8b | refiner.py planned | OK |
| AC8b | TASK 3 | T-8c/T-8d | refiner.py planned | OK |
| AC9 | TASK 3 | T-9 | refiner.py planned | OK |
| AC10 | TASK 3 | T-10 | design says page FIRST | OK |
| AC11 | TASK 2 | T-11 | compiler `_canonical_rel_path` module-scope | OK |
| AC12 | TASK 2 | T-12/T-12b/T-12c | pipeline.py | BLOCK: wrong call shape |
| AC13 | TASK 2 | T-13/a/b/c | compiler.py | OK |
| AC15 | TASK 4 | 4 owner-module tests | listed test files | OK |
| AC16 | TASK 4 | behavioural + docstring | mcp/core.py | OK |
| AC17 | TASK 5 | cleanup implied | tests grep | BLOCK: count/scope false |
| AC18 | TASK 5 | lint test | tests grep | AMEND with corrected scope |
| AC19 | TASK 6 | e2e tests | tests planned | OK |
| AC20 | TASK 1/6 | T-20 | pipeline.py | OK |
| AC14-anchor | TASK 6 | anchor test | compiler.py | OK |

## Threat coverage matrix
| T# | mitigation in plan | verify in plan | status |
|----|--------------------|----------------|--------|
| T1 | chunk cap, `re.escape`, title cap | T-4 + greps | OK |
| T2 | says inherited `_mask_code_blocks` only | no sanitizer grep/test for `replace("\x00", "")` | BLOCK |
| T3 | keyword-only, validation, alias/threading | T-12/T-13; grep partial | OK, but docstring MUST say opaque/not trusted |
| T4 | page-FIRST per final design, hold-through history span | T-10 + docstring | OK; threat-model history-FIRST text is stale and dismissed by final design AC10 |
| T5 | `append_wiki_log` batch line | T-20 | OK |

## Conditions matrix
| condition | plan section | status |
|-----------|--------------|--------|
| 23 ACs map to clusters | TASK 1-6 | OK |
| ReDoS budget 500 x 200 | TASK 1 | OK |
| refiner lock nest page OUTER/history INNER hold-through | TASK 3 | OK |
| AC16 behavioural PROJECT_ROOT patch | TASK 4 | OK |
| AC12 dual-write both sites | TASK 2 | BLOCK: concept yes, call shape wrong |
| AC1b under-lock rederive | TASK 1 | OK |
| AC4b cap + warn | TASK 1 | OK |
| AC8 attempt_id | TASK 3 | OK |
| AC13 test triplet | TASK 2 | OK |
| AC15 atomic commit | TASK 4/commit plan | OK |
| drop `raising=False` | TASK 4 | OK |
| AC17 count reconciled | TASK 5 | BLOCK |
| AC19 no TimeoutError assertion | TASK 6 | OK |
| vacuous revert checks T-2/T-4/T-6/T-12b/T-15 | TASK 1/2/4 | AMEND: T-4/T-15 revert-checks not explicit enough |
| constants in `kb.config` | TASK 1 | OK |
| Evidence Trail sentinel discipline | global conditions | OK |
| Dependabot four-gate | design only, absent from plan | AMEND |

## Gaps (if REJECT)
- AC12 / Condition 5 / TASK 2: live signature is `_check_and_reserve_manifest(source_hash, source_ref, manifest_path=None)`, but plan snippet calls `_check_and_reserve_manifest(manifest_ref, pre_hash, manifest_path)`. Amend to call `_check_and_reserve_manifest(source_hash, manifest_ref, manifest_path?)` and preserve duplicate-check semantics.
- T2 / AC1 / TASK 1: threat model requires null-byte title sanitization plus grep verification. Plan only cites inherited masking. Add entry sanitizer and T-1 variant/grep.
- AC17 / Condition 12 / TASK 5: current grep does not support 6 intersection files. Re-scope cleanup from actual patch/fixture overlap, not the stale list.
- T3 / TASK 2: add explicit `ingest_source` docstring language: `manifest_key` is an opaque dict key from `manifest_key_for`, not trusted input and not a path.
- Condition 14 / TASK 1/4: state revert-checks explicitly for T-4 and all four T-15 callable families.
- Condition 17 / Global conditions: copy Dependabot four-gate into plan or explicitly mark out of scope for cycle 19 implementation.

## Grep confirmation log
- `_check_and_reserve_manifest` at `src/kb/ingest/pipeline.py:258`; caller at `src/kb/ingest/pipeline.py:1093` as `_check_and_reserve_manifest(source_hash, source_ref)`.
- `make_source_ref` at `src/kb/ingest/pipeline.py:35` import and `src/kb/ingest/pipeline.py:1063` build.
- `manifest[source_ref]` at `src/kb/ingest/pipeline.py:287` reservation and `src/kb/ingest/pipeline.py:1309` tail confirmation.
- `_canonical_rel_path` is module-scope at `src/kb/compile/compiler.py:50`.
- `_mask_code_blocks` and `_check_not_in_wikilink` are module-scope reusable helpers at `src/kb/compile/linker.py:53` and `src/kb/compile/linker.py:24`.
- `HASH_MANIFEST` patch sites: 12 real patch calls in 5 files; 8 files by literal grep including comments/docstrings.
- `tmp_kb_env` consumers: 7 files excluding `tests/conftest.py`.
- intersection: 1 real patch-file consumer (`tests/test_cycle13_frontmatter_migration.py`); 3 by literal grep, including comment/docstring-only files.
