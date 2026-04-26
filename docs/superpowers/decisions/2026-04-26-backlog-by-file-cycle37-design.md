# Cycle 37 — Brainstorming + Design Eval (R1+R2 consolidated) + Decision Gate

**Date:** 2026-04-26
**Cycle:** 37 — POSIX symlink security fix + requirements split
**Format:** Consolidated Steps 3-5 per cycle-36 L2 (tightly-scoped review work goes primary-session). Operator holds full context from cycle-36 close + Step-1 + Step-2.

## Step 3 — Brainstorming (≥2 approaches per area)

### Area A — POSIX symlink containment fix

**Approach A1 — Reorder `is_symlink()` BEFORE `.resolve()` (RECOMMENDED).**
Capture link-status on the literal candidate path BEFORE resolving. Simple, minimal-diff (~10 lines), preserves existing skip-with-error-row UX.

```python
candidate_path = effective_project_root / source_ref
is_link = candidate_path.is_symlink()
source_path = candidate_path.resolve()
if is_link:
    try:
        source_path.relative_to(raw_dir.resolve())
    except ValueError:
        # log + skip + continue (existing UX preserved)
```

**Approach A2 — `os.lstat()` + `stat.S_ISLNK`.**
More correct on edge cases (e.g., link-to-link chains where `Path.is_symlink()` may behave differently across Python versions). But adds a dependency on `stat` module + 2-3 extra lines for stat-bit handling. Diff is ~20 lines.

**Approach A3 — Resolve once, then re-check via `os.path.realpath` + `os.readlink`.**
Detect link by comparing candidate vs. resolved path. Brittle on Windows where junctions vs. symlinks differ; explicitly out of scope for cycle 37 (Windows symlink semantics are a separate cycle).

**Recommendation:** A1. Lowest blast radius, smallest diff, identical behavior to A2 in our use case (no link chains expected in `raw/`).

### Area B — Requirements file split structure

**Approach B1 — Replace `requirements.txt` with a shim that includes all 6 new files (Step-1 AC7 original).**
Lean. Single source of truth. But changes existing `pip install -r requirements.txt` semantics: the current 295-line FROZEN snapshot (transitive `==` pins for reproducibility) becomes a 6-line shim of `>=` specifiers. Pip resolver picks LATEST compatible versions on every install — version drift across developer machines.

**Approach B2 — Keep `requirements.txt` UNCHANGED (the 295-line frozen snapshot); add 6 new files alongside (RECOMMENDED).**
Backward compat for `pip install -r requirements.txt` (reproducibility preserved). New files are an additive workflow for users who want lean installs (`pip install -r requirements-runtime.txt` for production deploys; `pip install -r requirements-runtime.txt -r requirements-hybrid.txt` for hybrid only). Also matches the pattern used by ~80% of OSS Python projects with extras (e.g., FastAPI's `requirements*.txt` family).

**Approach B3 — Generate per-extra files from `pyproject.toml` via a tooling script.**
Eliminates drift between `pyproject.toml` and `requirements*.txt`. But requires a new tool dep (e.g., `pip-tools`), runtime hook, or pre-commit script. Adds maintenance overhead for marginal gain. Out of scope for cycle 37; cycle-38+ candidate if drift becomes painful.

**Recommendation:** B2. Preserves reproducibility, additive (zero-disruption to existing workflows), README documents both paths.

### Area C — Regression test design

**Approach C1 — File-existence + grep-based content checks (RECOMMENDED).**
Per `feedback_inspect_source_tests`: source-file string-reads as test assertions are usually vacuous. BUT: file-existence assertions and `-r requirements-runtime.txt` first-line checks are NOT vacuous because reverting the cycle's commits would DELETE those files / lines. The check is "does the artifact this cycle creates still exist?" — different category from "does this string appear in source code?".

**Approach C2 — pip install dry-run check.**
Spawn `pip install --dry-run -r requirements-runtime.txt` in a subprocess; assert exit code 0. More semantically meaningful but adds 5-10s test runtime + network dep + flakiness on offline CI. Cycle-23 L2: stub return type + cycle-22 L1 `pip install --dry-run` discipline both apply — I'd need to mock the subprocess. Net cost outweighs benefit.

**Approach C3 — Static toml + manifest cross-check via `tomllib`.**
Parse `pyproject.toml` `[project.optional-dependencies]` and assert each key has a corresponding `requirements-{key}.txt` file with the same packages. Catches future drift (e.g., a new `[project.optional-dependencies]` key not mirrored). But locks future devs into the convention.

**Recommendation:** C1 + a lite C3 cross-check. File-existence + first-line `-r requirements-runtime.txt` + floor-pin presence + (lite C3) one assertion that the 5 known extras names are mirrored 1:1. Total ~5 assertions in one test file.

## Step 4 — R1 + R2 design eval (consolidated)

### R1 (architecture / framing role) — verifies design vs Step-1 ACs

| AC | R1 verdict | Note |
|---|---|---|
| AC1 | PASS | Reorder approach is minimal-diff, preserves existing UX. |
| AC2 | PASS | Skipif drop on test_qb_symlink_outside_raw_rejected is one-line; the second skipif (Windows-no-elevation) is correctly preserved. |
| AC3 | PASS | Positive-case symlink-inside-raw test is divergent against AC1 over-restriction (e.g., if AC1 incorrectly rejected ALL symlinks, AC3 would fail). |
| AC4 | PASS | Mirror pyproject [project] dependencies verbatim. 7 packages. |
| AC5 | PASS | Mirror pyproject [project.optional-dependencies] verbatim. 5 files × 3-7 packages each. |
| AC6 | PASS | Floor pin from cycle-35 L8 lives in requirements-eval.txt; regression test pins it. |
| AC7 | AMENDED | Original AC7 said "requirements.txt becomes a shim"; **revised: KEEP unchanged** to preserve reproducibility. README update (AC8) documents both options. |
| AC8 | PASS | README install section gains a "Lean install (cycle 37)" subsection alongside the existing "Full dev install". |
| AC9 | PASS | C1 + lite C3 approach. Five assertions, all divergent-fail under revert. |

**R1 amendment:** AC7 changes from "requirements.txt becomes a shim" to "requirements.txt UNCHANGED; new files are additive". Rationale at Q3 below.

### R2 (edge-cases / failure-modes / security role)

| Item | R2 finding |
|---|---|
| Edge case 1 | What if `effective_project_root` itself is a symlink? `Path.resolve()` follows it. Cycle-37 fix only addresses `raw/`-internal symlinks; project-root-is-symlink is a deeper concern (out of scope; existing cycle-15+ project-root tests already handle the documented case). |
| Edge case 2 | Symlink-to-symlink chain (`raw/a → raw/b → /etc/passwd`)? `Path.resolve()` follows the chain to the final target; AC1 fix verifies the FINAL target against `raw_dir`, so the chain is rejected if any link in the chain escapes. ✓ |
| Edge case 3 | Junction points on Windows? Out of scope per cycle-37 non-goals. Windows-elevation ALLOW_SYMLINK_TESTS gate already documents the Windows-specific path. |
| Edge case 4 | What if `raw_dir` is missing or doesn't resolve? Existing `raw_dir.resolve()` call already fires; if raw_dir is missing, `relative_to()` ValueErrors and the symlink is rejected (correct fail-closed). |
| Failure mode 1 | Per-extra file's `-r requirements-runtime.txt` line uses LF on Windows / CRLF on POSIX → pip handles either. ✓ |
| Failure mode 2 | User runs `pip install -r requirements-eval.txt` without `langchain-openai>=1.1.14` floor → resolver picks 1.1.10 (vulnerable). AC6 floor pin closes this. AC9 regression test pins it. |
| Failure mode 3 | Cycle-22 L4 mid-cycle CVE arrival between Step-2 baseline and Step-11 verification. Step-11 PR-CVE diff handles. |
| Security 1 | T1 closes with reorder + verification test. ✓ |
| Security 2 | New per-extra files don't introduce new attack surface — they reference packages already in pyproject.toml. ✓ |
| Performance 1 | AC1 reorder adds ONE `is_symlink()` syscall per source path. Negligible (microseconds; called per ~10 sources per page; review context generation is already 100ms+). |

**R2 amendment:** None. R2 verdict APPROVE on all R1 amendments.

## Step 5 — Decision Gate (Opus subagent — primary-session per cycle-36 L2)

### Open questions resolved

#### Q1 — AC1 fix shape

**OPTIONS:** (a) reorder `is_symlink()` before `.resolve()`, (b) `os.lstat() + stat.S_ISLNK`, (c) `os.path.realpath` comparison.

## Analysis

Option (a) is the minimal-diff, idiomatic Python `pathlib` solution. `Path.is_symlink()` documented behaviour: "Return True if the path points to a symbolic link, False otherwise" — this checks the path's link-status WITHOUT resolving the link. The bug at line 70 is precisely that `.resolve()` is called BEFORE `is_symlink()`, inverting the check. The fix is to capture link-status on the unresolved path FIRST.

Option (b) using `os.lstat() + stat.S_ISLNK` is more low-level but produces identical observable behaviour for our case. The added complexity (importing `stat`, dispatching on stat-bits) only matters in edge cases like ACL-bearing files on NTFS — not in scope. Option (c) is fragile on Windows due to junction-vs-symlink semantics.

**DECIDE:** Option (a).
**RATIONALE:** Smallest diff, idiomatic, preserves existing UX. Cycle-36 L1 — minimum-viable fix.
**CONFIDENCE:** HIGH.

#### Q2 — AC4 dependency selection (which packages go into `requirements-runtime.txt`)

**OPTIONS:** (a) verbatim from `pyproject.toml [project] dependencies` (7 packages), (b) verbatim plus a few "obviously-runtime" packages from the current 295-line `requirements.txt` snapshot (e.g., `aiohttp`, `pydantic`).

## Analysis

Option (a) treats `pyproject.toml` as the source of truth. If a package is needed at runtime, it should be in `[project] dependencies` — the fact it's in the 295-line snapshot is incidental (it's a transitive dep of one of the 7 named runtime packages). Pip resolver handles transitives from the 7 names automatically.

Option (b) double-pins — risks drift between `pyproject.toml` and `requirements-runtime.txt`. If a future cycle bumps a runtime dep in `pyproject.toml` but forgets to update `requirements-runtime.txt`, the per-extra files lag behind.

**DECIDE:** Option (a).
**RATIONALE:** `pyproject.toml [project] dependencies` is canonical. Mirror verbatim. Drift is detected by AC9 cross-check.
**CONFIDENCE:** HIGH.

#### Q3 — AC7 `requirements.txt` shim vs unchanged

**OPTIONS:** (a) replace with shim referencing all 6 new files, (b) keep unchanged (the 295-line frozen snapshot).

## Analysis

Option (a) trades reproducibility for tidiness. The current 295-line `requirements.txt` is `pip freeze`-style: every transitive dep pinned to an exact version. This is the artifact developers and CI use to get a reproducible install. Replacing it with `-r requirements-runtime.txt` (specifiers `>=`) means pip resolves to LATEST compatible versions on every install — a NEW source of "works on my machine" / "broke in CI today but worked yesterday" bugs.

Option (b) is additive: keep the snapshot unchanged, add the new files for users who want lean installs. README (AC8) documents both paths. No backward-compat break. New workflow is opt-in.

The user has consistently flagged CI-cost concerns (cycle-36 "endless CI failure job runs"). Replacing a stable artifact with one that introduces version drift is exactly the kind of change that produces unexpected CI failures.

**DECIDE:** Option (b).
**RATIONALE:** Backward compat preserved. Additive workflow. AC7 amended to "requirements.txt UNCHANGED".
**CONFIDENCE:** HIGH.

#### Q4 — AC9 test approach

**OPTIONS:** (a) file-existence + grep-based content checks, (b) pip install dry-run subprocess, (c) tomllib cross-check parsing pyproject.toml.

## Analysis

Option (a) — file-existence assertions are NOT vacuous in this context. Reverting the cycle deletes the new files; the file-existence assertion fails. First-line `-r requirements-runtime.txt` check is also divergent (revert AC4 → first line is something else). Floor-pin grep is divergent (revert AC6 → grep returns no match). All three assertions are revert-DETECTING.

Option (b) is semantically richer but adds 5-10s runtime, network dep, flakiness. Net negative.

Option (c) catches FUTURE drift (a new pyproject extras key without a mirror file). Worth adding as one assertion in addition to (a).

**DECIDE:** (a) + lite (c). Five assertions: (1) all 6 files exist; (2) each per-extra file starts with `-r requirements-runtime.txt`; (3) `langchain-openai>=1.1.14` in `requirements-eval.txt`; (4) tomllib cross-check that all 5 `[project.optional-dependencies]` keys have matching `requirements-{key}.txt` files; (5) `requirements.txt` (the snapshot) unchanged structure (still 200+ lines, NOT a shim).
**RATIONALE:** Each assertion is divergent-fail. Lite (c) catches future drift cheaply.
**CONFIDENCE:** HIGH.

#### Q5 — Per-extra file pin style: exact `==` vs specifier `>=`

**OPTIONS:** (a) exact pins from current 295-line snapshot, (b) specifiers from pyproject.toml.

## Analysis

The new per-extra files' purpose is "I want a lean install of just the [hybrid] feature". Users wanting reproducibility use `requirements.txt` (the snapshot). The specifier-style files mirror `pyproject.toml` semantics — same as `pip install .[hybrid]` would resolve. Consistent with the canonical extras-install path.

**DECIDE:** Option (b). Specifiers `>=` from pyproject.toml.
**RATIONALE:** Matches `pip install .[extra]` semantics. Mirroring is one source of truth.
**CONFIDENCE:** HIGH.

#### Q6 — Should I run pip install on the new files at Step 9 to verify resolution?

**OPTIONS:** (a) yes, (b) no (skip), (c) dry-run only.

## Analysis

Option (a) installs each file into the venv → version churn → pytest re-runs → potential breakage of unrelated tests. High risk.

Option (b) trusts pip resolver to handle version specifiers correctly (it does — pyproject extras work the same way). The 6 new files mirror pyproject; if pip can resolve `pip install .[hybrid]`, it can resolve `pip install -r requirements-hybrid.txt`. Symmetry argument.

Option (c) `pip install --dry-run` adds CI time. Cycle-22 L1 noted `--dry-run` is brittle on resolver-conflict cases. Cycle-34 L1 refined this. Skip per CI-cost discipline.

**DECIDE:** Option (b).
**RATIONALE:** Trust the resolver — same shape as pyproject extras. AC9 file-existence + cross-check tests catch the structural drift class. Resolution failure surfaces at user-install time and is corrigible via cycle-N+1 fix-shape.
**CONFIDENCE:** MEDIUM-HIGH.

## VERDICT

**APPROVE** all 9 ACs with one amendment (AC7 from "shim" to "unchanged"). Proceed to Step 6 → Step 7.

## DECISIONS summary

- AC1: Reorder is_symlink() before .resolve()
- AC2: Drop POSIX-only skipif on test_qb_symlink_outside_raw_rejected
- AC3: Add positive-case test_qb_symlink_inside_raw_accepted
- AC4: requirements-runtime.txt mirrors pyproject [project] dependencies (7 packages, specifiers)
- AC5: 5 per-extra files mirror pyproject [project.optional-dependencies]
- AC6: requirements-eval.txt has langchain-openai>=1.1.14 floor pin
- AC7 AMENDED: requirements.txt UNCHANGED (snapshot preserved); new files are additive
- AC8: README install section documents BOTH old (`pip install -r requirements.txt`) AND new (`pip install -r requirements-runtime.txt + per-extra`) options
- AC9: 5-assertion regression test (file-existence + first-line + floor-pin + tomllib cross-check + requirements.txt-still-snapshot)

## CONDITIONS (Step 9 must satisfy)

1. AC1 fix MUST capture `is_symlink()` BEFORE calling `.resolve()` — order matters per Q1.
2. AC2 drops EXACTLY one skipif marker (the `os.name != "nt"` one); the Windows-no-elevation skipif stays.
3. AC3 positive-case test asserts `s.get("content") == <expected>` (NOT `!= "SECRET DATA"`) — divergent against AC1 over-restriction.
4. AC4 file lists 7 packages from pyproject.toml [project] dependencies; NO transitive packages (`pyyaml-include`, `httpx`, etc.) added.
5. AC6 grep target is the literal string `langchain-openai>=1.1.14` in `requirements-eval.txt` (not just `langchain-openai`).
6. AC7 condition: `requirements.txt` line count BEFORE = line count AFTER (snapshot preserved). Test (5) asserts line count > 100.
7. AC9 test file is named `tests/test_cycle37_requirements_split.py` per cycle-26 L3 (canonical name).

## FINAL DECIDED DESIGN

The 9 ACs above with R1+R2 amendments encoded. No deferrals. Cycle 37 ships 4 production-touching changes (1 src/kb/ fix + 6 new requirements files + 1 README change + 1 test file) and zero CI workflow changes per cycle-36 L1.
