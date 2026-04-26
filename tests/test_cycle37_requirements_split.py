"""Cycle 37 regression tests — requirements file split structure.

AC9: pin the cycle-37 requirements split contract:
- requirements-runtime.txt mirrors pyproject [project] dependencies
- 5 per-extra files mirror pyproject [project.optional-dependencies] keys
- Each per-extra file -r-includes requirements-runtime.txt
- requirements-eval.txt carries the cycle-35 L8 langchain-openai>=1.1.14 floor pin
- requirements.txt remains the FROZEN snapshot (Q3 amendment — NOT a shim)
- pyproject extras keys match the per-extra file set 1:1 (cross-check for future drift)

Each assertion is divergent-fail: reverting the cycle's commits flips at least
one assertion (file deleted, line missing, structure changed).
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPECTED_EXTRAS = ("hybrid", "augment", "formats", "eval", "dev")


def test_runtime_file_exists_and_no_self_include():
    """AC4: requirements-runtime.txt exists; does NOT -r-include itself."""
    runtime = PROJECT_ROOT / "requirements-runtime.txt"
    assert runtime.exists(), (
        "requirements-runtime.txt missing — cycle-37 AC4 reverted? "
        "Per-extra files all -r-include this; deletion breaks them."
    )
    text = runtime.read_text(encoding="utf-8")
    assert "-r requirements-runtime.txt" not in text, (
        "requirements-runtime.txt MUST NOT -r-include itself (cycle would loop)"
    )
    # Spot-check known runtime deps from pyproject [project] dependencies
    assert "click" in text, "Runtime file missing click (pyproject [project] dependency)"
    assert "anthropic" in text, "Runtime file missing anthropic (pyproject [project] dependency)"


def test_per_extra_files_exist_and_include_runtime():
    """AC5: 5 per-extra files exist and each starts with -r requirements-runtime.txt."""
    for extra in EXPECTED_EXTRAS:
        path = PROJECT_ROOT / f"requirements-{extra}.txt"
        assert path.exists(), (
            f"requirements-{extra}.txt missing — cycle-37 AC5 reverted? "
            f"Each per-extra file mirrors pyproject [project.optional-dependencies].{extra}"
        )
        text = path.read_text(encoding="utf-8")
        assert "-r requirements-runtime.txt" in text, (
            f"requirements-{extra}.txt MUST -r-include requirements-runtime.txt "
            f"(layered install pattern)"
        )


def test_eval_file_pins_langchain_openai_floor():
    """AC6: cycle-35 L8 floor pin propagates from pyproject to requirements-eval.txt.

    Closes GHSA-r7w7-9xr2-qq2r (DNS-rebinding SSRF in langchain-openai's
    image-token-counting helper, fix at 1.1.14). Without the pin, pip resolver
    on requirements-eval.txt may pick 1.1.10 (vulnerable).
    """
    eval_path = PROJECT_ROOT / "requirements-eval.txt"
    text = eval_path.read_text(encoding="utf-8")
    assert re.search(r"^langchain-openai>=1\.1\.14", text, re.MULTILINE), (
        "requirements-eval.txt missing langchain-openai>=1.1.14 floor pin "
        "(cycle-35 L8). Resolver may pick 1.1.10 (GHSA-r7w7-9xr2-qq2r)."
    )


def test_pyproject_extras_match_per_extra_files():
    """Cross-check: every [project.optional-dependencies] key has a mirror file.

    Detects future drift — adding a new pyproject extra without a mirror file
    surfaces here as a set-equality failure.
    """
    pyproject = PROJECT_ROOT / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    extras_keys = set(data["project"]["optional-dependencies"].keys())
    expected = set(EXPECTED_EXTRAS)
    assert extras_keys == expected, (
        f"pyproject extras keys {sorted(extras_keys)} differ from expected "
        f"{sorted(expected)}; if adding a new extra, also add "
        f"requirements-<key>.txt and update EXPECTED_EXTRAS in this test."
    )


def test_requirements_txt_remains_snapshot():
    """AC7 (Q3 amendment): requirements.txt is the FROZEN snapshot, NOT a shim.

    The 295-line snapshot provides reproducibility (transitive == pins) for
    `pip install -r requirements.txt` workflows. Replacing it with a 6-line
    shim of `-r` references would re-introduce version drift.
    """
    req = PROJECT_ROOT / "requirements.txt"
    text = req.read_text(encoding="utf-8")
    line_count = sum(1 for ln in text.splitlines() if ln.strip() and not ln.startswith("#"))
    assert line_count > 100, (
        f"requirements.txt has only {line_count} non-comment lines; "
        "AC7 says snapshot must be preserved. Did someone replace it with a shim? "
        "If so, this regression test surfaced the change — confirm intent and "
        "update test expectation OR restore the snapshot."
    )


def test_tomllib_available_on_supported_python():
    """Sanity: cycle-37 test relies on tomllib (stdlib since 3.11).

    pyproject.toml requires-python = '>=3.12', so tomllib is always present.
    This assertion guards against an accidental sys.version_info gate elsewhere.
    """
    assert sys.version_info >= (3, 11), "tomllib requires Python 3.11+"
    # tomllib already imported at module top; if import failed, collection fails
    assert tomllib is not None
