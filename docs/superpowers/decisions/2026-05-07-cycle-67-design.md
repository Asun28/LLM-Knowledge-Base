# Cycle 67 — Step 5 Design Decision

**Date:** 2026-05-07
**Pipeline step:** 5 (Design decision gate)
**Owner:** Opus 4.7 main session (consolidation; Step 2 subagent hang at 23 min triggered cycle-20 L4 fallback for related authorship)
**Inputs:**
- Requirements: `2026-05-07-cycle-67-requirements.md` (15 ACs)
- Brainstorm: `2026-05-07-cycle-67-brainstorm.md` (design picks for AC01/03/07/12/14)
- R1 review: `2026-05-07-cycle-67-design-eval-R1-opus.md` (Opus 4.7, 10 conditions)
- R2 review: `2026-05-07-cycle-67-design-eval-R2-deepseek.md` (DeepSeek V4 Pro, 18 findings — 4 BLOCKER, 6 MAJOR, 8 MINOR — 11 conditions)
- Threat model: `2026-05-07-cycle-67-threat-model.md` (15 STRIDE threats 1:1 to ACs + 3 patchable CVEs)

## Verdict

**APPROVE-WITH-INLINE-RESOLUTIONS.**

All 28 findings resolvable via inline resolutions. Zero re-architecture required. Zero new ACs added. Step 7 implementation plan can lock against this consolidated CONDITIONS list.

R1's 10 conditions and R2's 11 conditions overlap on 2 items (Windows kill semantics + AC11 grep false-positives). After dedup: 19 total conditions.

## Inline resolutions

### R1 conditions

| ID | Severity | Resolution | Sub-AC pin |
|----|----------|------------|------------|
| R1-F1 / C1 — AC03 stdin-write starvation | BLOCKER | **ACCEPT** — use `proc.stdin.write/close` separately from daemon stdout/stderr readers; do NOT call `proc.communicate(input=...)`. | AC03-T-stdin-overflow |
| R1-F2 / C2 — AC03 Windows kill grace | BLOCKER | **ACCEPT** — `sys.platform.startswith("win")` branch. POSIX: `terminate(); wait(2); kill()`. Windows: `terminate(); wait(0.5)`. | AC03-T-platform-branch |
| R1-F3 / C3 — AC04 truthiness convention | MAJOR | **ACCEPT** — `os.environ.get('KB_STRICT_PUBLISH', '').strip().lower() in ('1', 'true', 'yes')`. Symmetric with AC06. | AC04-T-truthy-variants |
| R1-F4 / C4 — AC12 transition path | MAJOR | **ACCEPT** — Step 7 first task: run audit, count offenders. If N==0, ship hard-fail. If N>0, ship warn-only AND BACKLOG entry with cycle-68-70 expected resolution. | Step-7-task-0 |
| R1-F5 / C5 — AC07 PyYAML dep verify | MAJOR | **ACCEPT** — verified PyYAML 6.0.3 is installed in current venv. Step 7 plan task: confirm transitive availability. If absent from BOTH direct and transitive, add `PyYAML>=6.0` to install_requires. | Step-7-task-1 |
| R1-F6 / C6 — AC03 stderr cap symmetry | MAJOR | **ACCEPT** — introduce `MAX_CLI_STDERR_BYTES = 64 * 1024` constant in config.py. stderr daemon caps at this value. | AC03-T-stderr-volume |
| R1-F7 / C7 — AC09 dual coverage | MINOR | **ACCEPT** — both T*A (input mutation) AND T*B (renderer mutation) per snapshot subject. | AC09-T-dual |
| R1-F8 / C8 — AC11 dynamic grep value | MINOR | **ACCEPT** — extract dummy-key value dynamically from ci.yml; allowlist legitimate doc references (BACKLOG.md, CHANGELOG.md, CHANGELOG-history.md, docs/reference/testing.md, docs/superpowers/decisions/*). | AC11-T-doc-allowlist |
| R1-F9 / C9 — AC02 aliased import | MINOR | **ACCEPT** — only `from kb.graph.cache import get_graph` is forbidden. Pin a positive test for aliased form. | AC02-T-aliased-allowed |
| R1-F10 / C10 — Commit order swap | NIT | **ACCEPT** — workflow-only changes (AC10, AC11) commit BEFORE AC09 so CI cannot mask AC09's divergent-fail. | (commit ordering, no test) |

### R2 findings

| ID | Severity | Resolution | Sub-AC pin |
|----|----------|------------|------------|
| R2-F1 — AC01 dict() conversion | MAJOR | **MODIFY** — `dict(MODEL_TIERS)` SHOULD work via `__iter__` + `__getitem__` protocol. Pin a test asserting it reads env at conversion time. | AC01-T-dict-conversion |
| R2-F2 — AC01 missing dict methods | MAJOR | **ACCEPT + MODIFY** — implement `.keys()`, `.values()`, `.items()` via `collections.abc.Mapping` mixin. All reads env-dynamic. | AC01-T-mapping-methods |
| R2-F3 — AC01 equality | MINOR | **ACCEPT** — `_ModelTiersView()` is NOT `==` to a dict literal. Document: "use `dict(MODEL_TIERS) == {...}` to compare contents." | AC01-T-eq-not-supported |
| R2-F4 — AC01 iteration order | MINOR | **ACCEPT** — `__iter__` returns `iter(_DEFAULT_MODEL_TIERS)` (preserves insertion order). Pin a test. | AC01-T-iter-order |
| R2-F5 — AC01 serialization | MINOR | **ACCEPT** — operators wanting JSON serialize via `json.dumps(dict(MODEL_TIERS))`. Pin a test. | AC01-T-json-roundtrip |
| R2-F6 — AC03 stdin deadlock | BLOCKER | **MERGE** with R1-F1 (same root cause). | AC03-T-stdin-overflow |
| R2-F7 — AC03 Windows race | BLOCKER | **MERGE** with R1-F2. | AC03-T-platform-branch |
| R2-F8 — AC03 tracemalloc Windows | MINOR | **ACCEPT** — document scope: parent-process allocations only. | AC03-T-memory-doc |
| R2-F9 — AC03 error-kind preservation | MAJOR | **ACCEPT** — Popen refactor preserves all `LLMError` `kind=` paths: `not_installed`, `timeout`, generic exit-code-non-zero. | AC03-T-error-kinds |
| R2-F10 — AC05 MCP response sanitization | BLOCKER | **ACCEPT** — invoke through MCP boundary (`_mcp_error_boundary` decorated function), not just `VectorIndex.build()`. Asserts response string contains no path. | AC05-T-mcp-boundary |
| R2-F11 — AC07 YAML unsafe_load RCE | BLOCKER | **ACCEPT** — `yaml.safe_load` ONLY. Pin malicious-payload test (`!!python/object/new:os.system`). | AC07-T-safe-load |
| R2-F12 — AC07 incomplete error coverage | MAJOR | **ACCEPT** — three fallback tests: file-not-found, malformed-YAML, I/O permission. | AC07-T-fallback-trio |
| R2-F13 — AC07 schema validation | MINOR | **ACCEPT** — when `duplicate_slug_allowlist` is not list-of-pairs, log warning + fall through. | AC07-T-schema |
| R2-F14 — AC07 call-time perf | MINOR | **ACCEPT** — document one stat() + small file read per `check_duplicate_slugs` call. | (docs only) |
| R2-F15 — AC11 grep comment FP | MINOR | **MERGE** with R1-F8. | AC11-T-doc-allowlist |
| R2-F16 — AC12 generator raises | MAJOR | **ACCEPT** — for generator functions (those that `yield`), `Raises:` required if body has any `raise`. | AC12-T-generator-raises |
| R2-F18 — AC14 reference-style links | MAJOR | **REJECT scope expansion** — CLAUDE.md uses inline-link only. Document in script comment. | (docs only) |
| R2-F19 — AC14 multilink per line | MINOR | **ACCEPT** — `re.findall` correctly handles multiple links per line. Pin a test. | AC14-T-multilink |

## CONDITIONS list (final, locked — 19 items)

| # | ID | AC | Source | Test pin |
|---|-----|-----|--------|----------|
| 1 | C-AC01-conv | AC01 | R2-F1 | `test_model_tiers_dict_conversion_reads_env` |
| 2 | C-AC01-map | AC01 | R2-F2 | `test_model_tiers_mapping_methods_env_dynamic` |
| 3 | C-AC01-eq | AC01 | R2-F3 | `test_model_tiers_eq_to_dict_not_supported` |
| 4 | C-AC01-iter | AC01 | R2-F4 | `test_model_tiers_iter_order_stable` |
| 5 | C-AC01-json | AC01 | R2-F5 | `test_model_tiers_json_via_dict_conversion` |
| 6 | C-AC02-alias | AC02 | R1-C9 | `test_cycle67_graph_cache_aliased_import_allowed` |
| 7 | C-AC03-stdin | AC03 | R1-C1, R2-F6 | `test_cli_backend_popen_large_stdin_plus_large_stdout` |
| 8 | C-AC03-platform | AC03 | R1-C2, R2-F7 | `test_cli_backend_popen_platform_kill_branch` |
| 9 | C-AC03-stderr | AC03 | R1-C6 | `test_cli_backend_popen_stderr_capped` |
| 10 | C-AC03-error-kinds | AC03 | R2-F9 | `test_cli_backend_popen_preserves_error_kinds` |
| 11 | C-AC04-truthy | AC04 | R1-C3 | `test_kb_strict_publish_truthy_variants` |
| 12 | C-AC05-mcp | AC05 | R2-F10 | `test_sqlite_vec_load_error_mcp_response_sanitized` |
| 13 | C-AC07-safe | AC07 | R2-F11 | `test_lint_yaml_rejects_malicious_payload` |
| 14 | C-AC07-fallback | AC07 | R2-F12 | `test_lint_yaml_{file_missing,parse_error,io_error}_falls_through` |
| 15 | C-AC07-schema | AC07 | R2-F13 | `test_lint_yaml_schema_mixed_type_warning` |
| 16 | C-AC09-dual | AC09 | R1-C7 | per-snapshot T*A AND T*B |
| 17 | C-AC11-allowlist | AC11 | R1-C8, R2-F15 | CI step assertion `test_ci_dummy_key_allowlist_doc_files` |
| 18 | C-AC12-generator | AC12 | R2-F16 | `test_audit_docstrings_generator_with_raise_requires_raises_section` |
| 19 | C-AC14-multilink | AC14 | R2-F19 | `test_docs_index_consistency_multilink_per_line` |

## Step-7 plan-dispatch instructions (forward-looking risks)

Mimo audit unlikely to catch without explicit guidance. Step 7 plan dispatch prompt MUST quote each FW item verbatim:

**FW-1: AC03 Popen reference implementation.** MUST split stdin write from stdout/stderr reads — do NOT use `proc.communicate(input=...)` with daemon readers (R1-F1).

**FW-2: AC07 YAML safe_load specificity.** MUST use `yaml.safe_load` ONLY; never `yaml.load` (R2-F11).

**FW-3: AC11 dummy-key grep regex breadth.** Dynamic value extraction + doc-file allowlist (R1-F8 + R2-F15).

**FW-4: AC12 generator + yield + raise.** Generators with `raise` in body need `Raises:` (R2-F16).

**FW-5: AC01 Mapping ABC vs plain class.** MANDATE `collections.abc.Mapping` (Approach B); avoid dict subclass C-level fast-path bypass.

**FW-6: Step-7 task ordering.** Per R1-C10: AC02 → AC08 → AC15 → AC10 → AC11 → AC09 → AC14 → AC12 → AC13 → AC04 → AC05 → AC07 → AC06 → AC01 → AC03.

## R3-trigger reaffirmation

Cycle 67 hits 15 ACs + 4 BLOCKERs from R2 + new security enforcement points (AC11 grep, AC12 audit, AC07 YAML safe_load) + new filesystem-write surface (AC07 _lint.yml). All four cycle-17 L4 risk-profile triggers met.

**Step 20 R3 is REQUIRED** (Sonnet edge-case role). Document trigger in PR body at Step 18.

## Step 14 verifier checklist

Inherited from threat model `## Step 14 verifier checklist` section. Step 14 subagent reads BOTH the threat model checklist AND the 19 CONDITIONS list above.

## Step 6 (Context7) — SKIP

All 15 ACs use stdlib (subprocess, ast, sqlite3, urllib.parse, ipaddress, importlib, re, pathlib, json, os, sys, threading, selectors, collections.abc) plus already-installed PyYAML. No new library dependencies. Step 4 absorbed Context7 pre-check.

## Step-5 verdict summary

- 15 ACs locked
- 19 CONDITIONS, all ACCEPT (with 5 MODIFY clarifications)
- 0 BLOCKER unresolved
- 0 architecture changes
- 6 forward-looking risks for Step 7 dispatch
- R3 review required at Step 20

Step 7 implementation plan can lock against this consolidated spec. Mimo Coding subagent dispatch prompt at Step 7 MUST include FW-1 through FW-5 verbatim per `project_cycle61_mimo_failure` memory (treat mimo Step 7/9 as failed-by-default).
