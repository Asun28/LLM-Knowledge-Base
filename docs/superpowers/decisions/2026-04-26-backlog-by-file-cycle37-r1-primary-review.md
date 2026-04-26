# Cycle 37 — R1 Primary-Session PR Review

**PR:** #51
**Reviewer:** Primary session (per cycle-36 L2 — tightly-scoped review work goes primary-session; subagent dispatch overhead exceeds value when primary holds full context).
**Branch:** `feat/backlog-by-file-cycle37`
**Three commits:** `ba6bfad` (security fix) → `5fa1c75` (requirements split) → `e0c2c69` (docs).
**Skip R3 trigger check (per cycle-17 L4):** 9 ACs (≤25), no new filesystem-write surface, no defensive check whose input is hard to reach, no NEW security enforcement point (AC1 fixes a dead-code containment check; doesn't introduce one). 6 design-gate questions resolved (≤10). Skip R3.

## Verdict: APPROVE

No blockers, no majors, no NITs requiring in-cycle fixes.

## Per-AC verification

| AC | Status | Evidence |
|---|---|---|
| AC1 | PASS | `src/kb/review/context.py:70-82` — `candidate_path = effective_project_root / source_ref` then `is_link = candidate_path.is_symlink()` then `source_path = candidate_path.resolve()`. Order matches design Q1 verbatim. The symlink-containment block at `:91-103` now uses the captured `is_link` flag and uses `source_path` (resolved) for the `relative_to(raw_dir.resolve())` check — semantically correct. |
| AC2 | PASS | `tests/test_phase45_theme3_sanitizers.py:395-406` — only the Windows-elevation skipif remains. Cycle-36 POSIX-only skipif removed (8-line block deleted). Comment block in the test docstring explains the cycle-37 transition. |
| AC3 | PASS | `tests/test_phase45_theme3_sanitizers.py:441-489` — new `test_qb_symlink_inside_raw_accepted`. Setup creates `raw/articles/alias.md → raw/sources/real.md` (target STAYS within `raw_dir`). Asserts `len(sources) == 1` AND `sources[0]["content"] == target_content` — divergent against an over-broad AC1 that would reject ALL symlinks. |
| AC4 | PASS | `requirements-runtime.txt` — 7 packages: click, python-frontmatter, fastmcp, networkx, anthropic, PyYAML, jsonschema. Verbatim mirror of `pyproject.toml [project] dependencies`. NO transitive packages double-pinned. |
| AC5 | PASS | 5 per-extra files exist; each starts with `-r requirements-runtime.txt` (verified locally via `head -1`). Comments explicitly cite `[project.optional-dependencies].<extra>` and the canonical `pip install .[extra]` equivalent. |
| AC6 | PASS | `requirements-eval.txt:13` — `langchain-openai>=1.1.14` with cycle-35 L8 GHSA-r7w7-9xr2-qq2r citation in the comment block above. |
| AC7 (Q3) | PASS | `git diff main..HEAD -- requirements.txt` shows zero changes. Frozen 295-line snapshot preserved. AC9 `test_requirements_txt_remains_snapshot` pins line-count > 100. |
| AC8 | PASS | `README.md:120-141` — install section now has "lean install (cycle 37)" + 5 per-feature lines + "canonical extras" subsections alongside the existing snapshot install. Backward-compat instructions preserved. |
| AC9 | PASS | `tests/test_cycle37_requirements_split.py` — 6 tests (5 invariants + 1 sanity tomllib import). Local pytest: `6 passed in 0.18s`. Each assertion is divergent-fail under cycle revert. |

## Per-CONDITION verification (Step-5 design gate)

| C | Status | Evidence |
|---|---|---|
| C1 | PASS | AC1 captures `is_symlink()` BEFORE `.resolve()`. Order verified at lines 71-73. |
| C2 | PASS | AC2 drops EXACTLY one skipif marker. Windows-elevation marker preserved at lines 395-398. |
| C3 | PASS | AC3 asserts content EQUALITY (`==`), NOT inequality — divergent against AC1 over-restriction. |
| C4 | PASS | AC4 lists 7 packages verbatim from pyproject.toml. No transitives like httpx, pydantic, etc. |
| C5 | PASS | AC6 grep target is the literal `langchain-openai>=1.1.14` (verified by `re.search(r"^langchain-openai>=1\.1\.14", text, re.MULTILINE)` in test). |
| C6 | PASS | AC7 condition: `requirements.txt` line count BEFORE = line count AFTER. Test asserts `line_count > 100` (snapshot is ~295 lines). |
| C7 | PASS | Test file named `tests/test_cycle37_requirements_split.py` per cycle-26 L3 canonical convention. |

## Architecture-level concerns

**Marker semantics correct.** The AC1 fix is the textbook reorder pattern — `is_symlink()` documents that it does NOT follow the link, while `Path.resolve()` does. The bug was a sequencing error, not a semantic misunderstanding. Cycle-23 L1 documented at the symbol-verification level; cycle-37 surfaces the operational consequence (dead-code containment).

**Additive vs replacement trade-off.** Q3's AC7 amendment from "shim" to "UNCHANGED" is the right call. The 295-line `requirements.txt` is a `pip freeze`-style snapshot for reproducibility; replacing it with a 6-line shim of `>=` specifiers re-introduces version drift. New per-extra files are additive — opt-in via `pip install -r requirements-runtime.txt -r requirements-hybrid.txt` for users who want lean installs. Both workflows coexist; README documents both.

**Test coverage shape.** All 6 cycle-37 tests are non-vacuous per cycle-15 L2 / cycle-24 L4: file-existence assertions hard-fail under revert; first-line `-r` checks fail if anyone re-orders the includes; floor-pin grep fails under cycle-35 L8 regression; tomllib cross-check fails on future drift; snapshot-line-count check fails if anyone replaces with a shim. AC1+AC2+AC3 symlink-test pair is divergent on POSIX (revert AC1 → secret content read → assertion flips).

## Edge cases

- Symlink chain (`raw/a → raw/b → /etc/passwd`): `Path.resolve()` follows the full chain to the final target; AC1's `relative_to(raw_dir.resolve())` check then verifies the FINAL target → chain is rejected if any link in the chain escapes. ✓
- `effective_project_root` itself a symlink: out of scope (cycle-15+ project-root tests already handle the documented case).
- `raw_dir` missing or doesn't resolve: existing `raw_dir.resolve()` behaviour preserved. If raw_dir is missing, `relative_to()` raises ValueError → symlink rejected (correct fail-closed). ✓
- Symlink to a file that doesn't exist: `Path.resolve()` returns the candidate (Python 3.6+ semantics). The subsequent `source_path.exists()` check at line 105 fires; symlink to nonexistent target is skipped via the existing flow.
- Per-extra file LF/CRLF: pip handles both line endings transparently. ✓
- Floor pin `langchain-openai>=1.1.14` in `requirements-eval.txt` AND `pyproject.toml [eval]`: dual-source is fine; both paths converge on the same constraint. AC9 cross-check would catch a drift.

## Threat-model verification (matches Step-11)

| T | Status | Note |
|---|---|---|
| T1 — POSIX symlink containment bypass | IMPLEMENTED | AC1 reorder verified above. |
| T2 — Backward-compat shim risk | IMPLEMENTED | AC7 unchanged; AC9 snapshot-preservation test pins. |
| T3 — Per-extra `-r` reference breakage | IMPLEMENTED | AC9 file-existence + first-line tests. |
| T4 — Cycle-35 L8 floor pin loss | IMPLEMENTED | AC6 + AC9 grep test. |
| T5 — Cycle-22 L4 mid-cycle CVE arrival | IMPLEMENTED | Step 11 PR-CVE diff: empty INTRODUCED set. |
| T6 — Skipif marker over-disable | IMPLEMENTED | AC2 verified (only Windows-elevation skipif remains). |
| T7 — README staleness | IMPLEMENTED | AC8 documents both old + new install paths. |

## Blockers / Majors / NITs

**Blockers:** None.

**Majors:** None.

**NITs (cosmetic, optional cycle-38 follow-up):**

- **N1.** Cycle-37 L1/L2 lessons identified at Step 16 commit: two-commit cycles + additive-vs-replacement principle. Worth elevating to feature-dev SKILL.md index.
- **N2.** `tests/test_cycle37_requirements_split.py::test_tomllib_available_on_supported_python` is essentially a sanity check. Could be removed if the test file's tomllib import statement is enough, but keeping it as a forward guard against future Python-version constraints is harmless (cycle-15 L2 DROP-with-test-anchor pattern variant).
- **N3.** README's new lean-install commands assume the user installs `pyyaml-include` etc. transitively. If a user wants TRULY minimal (e.g., only the 7 named runtime deps), pip will pull in the transitive closure. This is fine and documented behavior, but cycle-38+ could explore a `requirements-runtime-frozen.txt` for absolute reproducibility on the lean path.

**Out-of-scope reminders:**
- Windows-latest matrix re-enable: cycle 38+ per cycle-36 L1 deferral.
- `mock_scan_llm` POSIX reload-leak: cycle 38+ (investigation-heavy refactor).
- `TestExclusiveAtomicWrite` POSIX behavior: cycle 38+.
- Dependabot drift on 2 litellm GHSAs: cycle 38+ (monitor only; pip-audit doesn't surface them).

## R2 / R3 decision

R2: Skip (primary-session R1 covered both architecture + edge-cases; cycle-36 L2 + user CI-cost concerns).
R3: Skip per cycle-17 L4 (≤25 ACs + no new write surface + no NEW security enforcement point + ≤10 design Qs). 

## Final verdict: APPROVE — proceed to merge.
