# Cycle 37 — Requirements + ACs

**Date:** 2026-04-26
**Cycle:** 37 — Pre-Phase-5 BACKLOG batch (POSIX symlink security fix + requirements split)
**User intent:** "group work as many as backlog fix items (before Phase 5 items) and make sure follow skill workflow, all tests verified, doc updated, backlog cleaned and self improve skill run"
**Operational constraints (from cycles 35/36):**
- Cycle-36 L1: zero new CI dimensions in cycle 37 (no matrix expansion). User pushed back on "endless CI failure job runs"; adding a probe windows-latest job that hangs every push extends the pattern.
- Cycle-36 L2: tightly-scoped review work goes primary-session.
- `feedback_minimize_subagent_pauses`: long pauses feel broken; primary-session for ≤30-item review work.
- `feedback_batch_by_file`: target 30-40 items, ~15-20 files. Cycle 37 is intentionally smaller (~8 ACs) given user's recent fatigue + the security fix's high priority + the cycle-36 lessons about CI cost discipline.

## Problem

Cycle 36 closed strict-gate CI on ubuntu but surfaced a REAL production POSIX security gap in `pair_page_with_sources` that the Windows-only test discovery had hidden. The defensive symlink containment check at `src/kb/review/context.py:86-103` is dead code: `source_path = (project_root / source_ref).resolve()` at line 70 follows the symlink BEFORE `is_symlink()` is checked at line 86, so `source_path.is_symlink()` always returns False on the already-resolved path. A malicious symlink inside `raw/` pointing to project secrets (or outside the project root if a containing dir traversal also succeeds) gets read and embedded into the review context.

Additionally, cycle 36 deferred the `requirements.txt` split (AC14-AC17 per Q7=B) which is now a Phase 4.5 MEDIUM with a concrete fix-shape: split `requirements.txt` into a runtime base + 5 per-extra files mirroring the `[project.optional-dependencies]` declared in `pyproject.toml`.

## Non-goals

- **NOT re-enabling windows-latest CI matrix.** Per cycle-36 L1 + user's CI-cost feedback, adding a NEW CI dimension WHILE the windows-latest threading.py:355 hang is unfixed extends the failed-CI-run pattern. Defer to cycle 38 (or later) with a concrete fix-shape from a self-hosted Windows runner investigation.
- **NOT investigating the GHA-Windows multiprocessing spawn hang.** Requires self-hosted runner; out of scope.
- **NOT fixing the `mock_scan_llm` POSIX reload-leak.** Requires SDK injection refactor; defer to a dedicated cycle 38 sub-task per cycle-36 BACKLOG entry.
- **NOT fixing TestExclusiveAtomicWrite/TestWriteItemFiles POSIX behavior.** Investigation-heavy; defer per cycle-36 BACKLOG.
- **NOT patching litellm CVEs.** Blocked by `click<8.2` transitive vs our `click==8.3.2`. Continue to monitor; no upstream fix available within `click` constraint.
- **NOT changing the `[project.optional-dependencies]` extras structure.** Cycle 34 already shipped them; cycle 37 only mirrors them as separate requirements files for users who prefer `pip install -r` over `pip install .[extra]`.

## Acceptance criteria

### Area A — POSIX symlink security gap fix (3 ACs)

**AC1.** `src/kb/review/context.py::pair_page_with_sources` checks `is_symlink()` on the unresolved path BEFORE calling `.resolve()`. Concrete code shape:
```python
candidate_path = effective_project_root / source_ref
is_link = candidate_path.is_symlink()
source_path = candidate_path.resolve()
# Containment: symlinks must stay within raw_dir; non-symlinks within project_root
if is_link:
    try:
        source_path.relative_to(raw_dir.resolve())
    except ValueError:
        # log + skip + continue (preserves existing skip-with-error-row behaviour)
```
Pre-cycle-37: `source_path.is_symlink()` always False after `.resolve()`. Post-cycle-37: symlink target verified against `raw_dir.resolve()` BEFORE read.

**AC2.** Drop the `skipif(os.name != "nt")` marker on `tests/test_phase45_theme3_sanitizers.py::test_qb_symlink_outside_raw_rejected` (lines 399-408). Test now runs on POSIX and Windows-with-`ALLOW_SYMLINK_TESTS`. Test asserts `s.get("content") != "SECRET DATA"` — already DIVERGENT-fail per cycle-24 L4 (revert AC1 → secret content is read → assertion flips).

**AC3.** Add a positive-case test `test_qb_symlink_inside_raw_accepted` covering: symlink inside `raw/articles/foo.md → raw/sources/foo.md` (target STAYS within `raw_dir`). Asserts the symlinked content IS read, not skipped. Pins the contract that legitimate intra-`raw/` symlinks still resolve correctly. Same `skipif` profile as AC2 (POSIX or Windows-with-elevated).

### Area B — Requirements.txt split into per-extra files (5 ACs)

**AC4.** Create `requirements-runtime.txt` containing the production-only minimal dependency set (anthropic, click, pyyaml, pydantic, jsonschema, frontmatter, BeautifulSoup, etc. — NO eval/dev/optional packages). Sourced from `pyproject.toml [project] dependencies`.

**AC5.** Create 5 per-extra files: `requirements-hybrid.txt`, `requirements-augment.txt`, `requirements-formats.txt`, `requirements-eval.txt`, `requirements-dev.txt`. Each starts with `-r requirements-runtime.txt` and adds the extra-specific packages. Sourced from `pyproject.toml [project.optional-dependencies]`.

**AC6.** Cycle-35 L8 floor pin `langchain-openai>=1.1.14` lives in `requirements-eval.txt` (was in pyproject.toml `[eval]` extra; mirror to the per-extra file).

**AC7.** Update `requirements.txt` to be a SHIM: `-r requirements-runtime.txt` plus `-r requirements-dev.txt` (full-dev superset preserved for backward compat with existing `pip install -r requirements.txt` workflows).

**AC8.** README install section updated to document the new options:
- `pip install -r requirements-runtime.txt` (lean, no SDK extras)
- `pip install -r requirements-runtime.txt -r requirements-hybrid.txt` (with hybrid search)
- `pip install -e .[hybrid]` (canonical pyproject extras path — unchanged)

### Cycle 37 verification ACs (1 AC)

**AC9.** New regression test `tests/test_cycle37_requirements_split.py` asserts:
- All 6 new files exist (`requirements-runtime.txt`, 5 per-extra)
- Each per-extra file starts with `-r requirements-runtime.txt`
- `requirements.txt` shim references both runtime + dev
- Floor pin `langchain-openai>=1.1.14` is in `requirements-eval.txt`
- Tests are non-vacuous: revert AC4-AC7 → file-existence assertion fails

## Blast radius

- `src/kb/review/context.py` — 1 function modified (`pair_page_with_sources` symlink check reorder)
- `tests/test_phase45_theme3_sanitizers.py` — drop 1 skipif marker, add 1 positive-case test
- `tests/test_cycle37_requirements_split.py` — NEW file, ~5 assertions
- `requirements.txt` — convert to shim (3 lines)
- `requirements-runtime.txt` + `requirements-{hybrid,augment,formats,eval,dev}.txt` — NEW files, ~10-50 lines each
- `README.md` — install section update only

NO changes to `pyproject.toml` (extras structure stays), NO changes to `.github/workflows/ci.yml` (no new CI dimensions per cycle-36 L1), NO changes to `CLAUDE.md` Quick Reference test count (will update at Step 12 after final test count).

## Threat model preview (full at Step 2)

- T1 — POSIX symlink containment bypass (AC1 closes)
- T2 — Requirements split breaks existing `pip install -r requirements.txt` workflows (AC7 shim mitigates)
- T3 — `-r requirements-runtime.txt` references break under pip resolver if file missing (AC4 + AC9 file-existence regression test mitigates)
- T4 — Cycle-35 L8 floor pin lost in split (AC6 + AC9 regression test mitigates)
- T5 — Cycle-22 L4 mid-cycle CVE arrival (Step 2 baseline + Step 11 diff handle)

## Decision points for Step 5 design gate

1. AC1 fix shape: (a) reorder `is_symlink()` check vs. (b) parametric `Path.lstat()` + `S_ISLNK`. Both options work; (a) preserves existing skip-with-error-row UX; (b) is more correct with `os.lstat`-style semantics on edge cases.
2. AC4 dependency selection: which packages from `pyproject.toml [project] dependencies` go into `requirements-runtime.txt` vs. stay in `requirements-dev.txt`? E.g., `pytest` is dev-only.
3. AC7 shim contents: include all 5 extras OR only `runtime + dev`? `runtime + dev` matches the historical full-dev superset; including all 5 extras risks churn for users who specifically want `[hybrid]` only.
4. AC9 test approach: file-existence + grep-based content checks (simple, fast) OR import-and-resolve via `pip-tools` / `packaging` (heavyweight)? Default to grep per `feedback_inspect_source_tests` — but file-existence + line-content greps are NOT vacuous (a missing file hard-fails).
