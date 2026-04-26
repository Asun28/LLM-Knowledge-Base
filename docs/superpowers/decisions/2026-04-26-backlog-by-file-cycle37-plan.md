# Cycle 37 — Implementation Plan + Plan Gate

**Date:** 2026-04-26
**Cycle:** 37 — POSIX symlink security fix + requirements split
**Format:** Primary-session per cycle-14 L1 (operator holds context). 9 ACs grouped into 5 file-grouped tasks per `feedback_batch_by_file`.

## Task ordering rationale

Cycle 37 has 5 file-affecting tasks across 5 files (1 src + 1 test + 6 requirements + 1 README + 1 new test). Per `feedback_batch_by_file`: one commit per file (or per cluster). Order tasks by dependency:

1. **TASK 1** (production fix) — must land FIRST because TASK 2 (test re-enable) asserts the fix's behavior.
2. **TASK 2** (test re-enable + positive case) — depends on TASK 1.
3. **TASK 3** (requirements files) — independent of T1-T2; can be parallel but serialise for review clarity.
4. **TASK 4** (README) — depends on T3 (must reference the new files).
5. **TASK 5** (regression test) — depends on T3 (asserts the new files exist).

## TASK 1 — Production fix: reorder `is_symlink()` before `.resolve()`

**Files:** `src/kb/review/context.py` (1 file)
**Change:** Lines ~70-103 in `pair_page_with_sources`. Replace:
```python
source_path = (effective_project_root / source_ref).resolve()
# (existing relative_to project_root check)
if source_path.is_symlink():
    resolved_target = source_path.resolve()
    try:
        resolved_target.relative_to(raw_dir.resolve())
    except ValueError:
        # log + skip
```
with:
```python
candidate_path = effective_project_root / source_ref
is_link = candidate_path.is_symlink()
source_path = candidate_path.resolve()
# (existing relative_to project_root check stays at same position)
if is_link:
    try:
        source_path.relative_to(raw_dir.resolve())
    except ValueError:
        # log + skip (existing UX preserved)
```
**Test:** Existing `test_qb_symlink_outside_raw_rejected` (skipif removal in TASK 2) asserts `s.get("content") != "SECRET DATA"`.
**Criteria:** AC1.
**Threat:** T1.
**Verification post-implementation:** Run `pytest tests/test_phase45_theme3_sanitizers.py::test_qb_symlink_outside_raw_rejected -v` on Windows-with-elevation OR local POSIX (developer machine). Should PASS post-fix.

## TASK 2 — Test re-enable + positive case

**Files:** `tests/test_phase45_theme3_sanitizers.py` (1 file, 2 changes)
**Change A:** Drop the `skipif(os.name != "nt", reason="Cycle 36 AC11 — KNOWN POSIX SECURITY GAP...")` at lines 399-408. Keep the Windows-elevation skipif at lines 395-398.
**Change B:** Add new test `test_qb_symlink_inside_raw_accepted` after `test_qb_symlink_outside_raw_rejected`:
- Setup: `raw/articles/foo.md` symlinks to `raw/sources/foo.md` (target STAYS in raw_dir)
- Frontmatter `source: ["raw/articles/foo.md"]`
- Assert `result["source_contents"][0]["content"]` equals the target file's content (NOT None, NOT error)
- Same `skipif` profile as the negative test (Windows-no-elevation skipped, POSIX runs)

**Test (for TASK 1):** Already exists; this task re-enables it.
**Criteria:** AC2 (Change A) + AC3 (Change B).
**Threat:** T1 verification.
**Verification:** Run both tests on POSIX (or Windows-with-elevation). Both PASS.

## TASK 3 — Requirements split (6 new files)

**Files:** 6 new files at repo root: `requirements-runtime.txt`, `requirements-hybrid.txt`, `requirements-augment.txt`, `requirements-formats.txt`, `requirements-eval.txt`, `requirements-dev.txt`
**Change:** Create files mirroring `pyproject.toml` structure:

`requirements-runtime.txt` (NO `-r` reference; this is the base):
```
# Runtime-only dependencies — mirrors [project] dependencies in pyproject.toml.
# For full reproducibility (pinned transitives), use requirements.txt.
# For per-feature installs, layer with -r requirements-{hybrid,augment,formats,eval}.txt.
click>=8.0
python-frontmatter>=1.0
fastmcp>=2.0
networkx>=3.0
anthropic>=0.7
PyYAML>=6.0
jsonschema>=4.20
```

`requirements-hybrid.txt`:
```
-r requirements-runtime.txt
# Hybrid search (BM25 + vector) — mirrors [project.optional-dependencies] hybrid.
model2vec>=0.5.0
sqlite-vec>=0.1.0
numpy>=1.26
```

`requirements-augment.txt`:
```
-r requirements-runtime.txt
# Augment-mode web fetching — mirrors [project.optional-dependencies] augment.
httpx>=0.27
httpcore>=1.0
trafilatura>=1.12
```

`requirements-formats.txt`:
```
-r requirements-runtime.txt
# Notebook ingest — mirrors [project.optional-dependencies] formats.
nbformat>=5.0,<6.0
```

`requirements-eval.txt`:
```
-r requirements-runtime.txt
# Evaluation harness — mirrors [project.optional-dependencies] eval.
ragas>=0.4
litellm>=1.83
datasets>=4.0
# Cycle 35 L8 floor pin — closes GHSA-r7w7-9xr2-qq2r (DNS-rebinding SSRF in
# langchain-openai's image-token-counting helper). Pulled in transitively by
# ragas; floor pin prevents resolver from picking 1.1.10 (vulnerable).
langchain-openai>=1.1.14
```

`requirements-dev.txt`:
```
-r requirements-runtime.txt
# Dev tooling — mirrors [project.optional-dependencies] dev.
pytest>=7.0
pytest-timeout>=2.3
ruff>=0.4.0
pytest-httpx>=0.30
pip-audit>=2.10
build>=1.2
twine>=5.0
```

**Test:** TASK 5 regression test asserts file existence + content invariants.
**Criteria:** AC4 (runtime), AC5 (5 per-extra), AC6 (floor pin in eval).
**Threat:** T2 (mitigated via AC7 unchanged in TASK 0 = no-op), T3 (file-existence in AC9), T4 (floor pin in AC9).
**Verification:** `ls requirements-*.txt` shows 7 files (1 existing + 6 new). Each new file's first non-comment line is `-r requirements-runtime.txt` (except runtime itself).

## TASK 4 — README install section update

**Files:** `README.md` (1 file)
**Change:** Update the install section to document both old + new options. Add:
```
### Install

**Full reproducibility (recommended for development):**
```bash
pip install -r requirements.txt
pip install -e .
```

**Lean install (cycle 37, runtime-only):**
```bash
pip install -r requirements-runtime.txt
pip install -e .
```

**Per-feature install (cycle 37, e.g., hybrid search):**
```bash
pip install -r requirements-runtime.txt -r requirements-hybrid.txt
pip install -e .
```

**Canonical extras (pyproject.toml):**
```bash
pip install -e .[hybrid]    # or .[augment], .[formats], .[eval], .[dev]
```
```
**Test:** None (doc-only change). TASK 5 doesn't grep README.
**Criteria:** AC8.
**Threat:** T7.

## TASK 5 — Regression test

**Files:** `tests/test_cycle37_requirements_split.py` (1 new file)
**Change:** New test file with 5 assertions:
```python
"""Cycle 37 regression tests — requirements file split structure."""
from __future__ import annotations
import re
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # noqa: F401  # 3.12+ project, fallback unused

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPECTED_EXTRAS = ("hybrid", "augment", "formats", "eval", "dev")


def test_runtime_file_exists_and_no_self_include():
    runtime = PROJECT_ROOT / "requirements-runtime.txt"
    assert runtime.exists(), "requirements-runtime.txt missing — cycle-37 AC4 reverted?"
    text = runtime.read_text(encoding="utf-8")
    # Runtime is the base; must NOT include itself
    assert "-r requirements-runtime.txt" not in text, (
        "requirements-runtime.txt should not -r-include itself"
    )
    # Spot-check a known runtime dep
    assert "click" in text, "Runtime file missing click"


def test_per_extra_files_exist_and_include_runtime():
    for extra in EXPECTED_EXTRAS:
        path = PROJECT_ROOT / f"requirements-{extra}.txt"
        assert path.exists(), f"requirements-{extra}.txt missing — cycle-37 AC5 reverted?"
        text = path.read_text(encoding="utf-8")
        assert "-r requirements-runtime.txt" in text, (
            f"requirements-{extra}.txt missing '-r requirements-runtime.txt' include"
        )


def test_eval_file_pins_langchain_openai_floor():
    eval_path = PROJECT_ROOT / "requirements-eval.txt"
    text = eval_path.read_text(encoding="utf-8")
    # Cycle 35 L8 floor pin must propagate to per-extra file
    assert re.search(r"^langchain-openai>=1\.1\.14", text, re.MULTILINE), (
        "requirements-eval.txt missing langchain-openai>=1.1.14 floor pin "
        "(cycle-35 L8). Resolver may pick 1.1.10 (GHSA-r7w7-9xr2-qq2r)."
    )


def test_pyproject_extras_match_per_extra_files():
    """Cross-check: every [project.optional-dependencies] key has a mirror file."""
    pyproject = PROJECT_ROOT / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    extras_keys = set(data["project"]["optional-dependencies"].keys())
    expected = set(EXPECTED_EXTRAS)
    assert extras_keys == expected, (
        f"pyproject extras keys {extras_keys} differ from expected {expected}; "
        f"add a requirements-{{key}}.txt for any new extra."
    )


def test_requirements_txt_remains_snapshot():
    """AC7 condition: requirements.txt is the FROZEN snapshot, NOT a shim."""
    req = PROJECT_ROOT / "requirements.txt"
    text = req.read_text(encoding="utf-8")
    # The snapshot has 200+ lines of pinned transitives. A shim would be ~10 lines.
    line_count = sum(1 for ln in text.splitlines() if ln.strip() and not ln.startswith("#"))
    assert line_count > 100, (
        f"requirements.txt has only {line_count} non-comment lines; "
        "AC7 says snapshot must be preserved. Did someone replace it with a shim?"
    )
```

**Test:** Self-asserting (this IS the test).
**Criteria:** AC9.
**Threat:** T3 + T4 verification.
**Verification:** `pytest tests/test_cycle37_requirements_split.py -v` shows 5 passed.

## Plan Gate (Codex subagent — primary-session per cycle-36 L2)

### AC coverage check

| AC | Task | Coverage | Note |
|---|---|---|---|
| AC1 | T1 | YES | src/kb/review/context.py reorder |
| AC2 | T2-A | YES | skipif drop on negative test |
| AC3 | T2-B | YES | new positive-case test |
| AC4 | T3 | YES | requirements-runtime.txt |
| AC5 | T3 | YES | 5 per-extra files |
| AC6 | T3 | YES | floor pin in eval file |
| AC7 | (no-op) | YES | requirements.txt UNCHANGED — no task needed (per Q3 amendment) |
| AC8 | T4 | YES | README update |
| AC9 | T5 | YES | regression test (5 assertions) |

### Threat coverage check

| T | Mitigation | Task | Test |
|---|---|---|---|
| T1 | AC1 reorder | T1 | T2 (existing test re-enabled) + T2 (positive case) |
| T2 | AC7 unchanged (no-op) | — | T5 (snapshot-preserved assertion) |
| T3 | AC9 file-existence | T5 | T5 |
| T4 | AC6 floor pin | T3 | T5 (eval-file pin assertion) |
| T5 | Step-11 PR-CVE diff | (Step 11) | (Step 11) |
| T6 | AC2 correct skipif drop | T2-A | T2 (test runs on POSIX) |
| T7 | AC8 README update | T4 | (no test needed — doc-only) |

### Plan amendment check

No `PLAN-AMENDS-DESIGN` flags. The design Q3 amendment (AC7 unchanged) was resolved at design gate; the plan reflects it. Cycle-11 L3 split-verdict — no real dependency violation.

**VERDICT:** APPROVE. Proceed to Step 9.

## Implementation order

T1 → T2 → T3 → T4 → T5 (per dependency chain). Each task = one commit. Total 5 commits before Step 10 CI gate.

## Cycle-13 sizing self-check

- T1: ~10 LOC change in src/. Primary-session per cycle-13 L2. ✓
- T2-A: 8-line skipif drop. Primary. ✓
- T2-B: ~25 LOC new test. Primary. ✓
- T3: 6 new files, ~40 LOC total. Primary. ✓
- T4: ~25 LOC README change. Primary. ✓
- T5: ~50 LOC new test. Primary. ✓

All within cycle-13 L2 thresholds. No Codex dispatch needed at Step 9 per cycle-36 L2.
