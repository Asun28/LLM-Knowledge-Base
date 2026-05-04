"""Cycle 65 AC2: Test no direct imports of MODEL_TIERS outside config.py (C3)."""

import sys
from pathlib import Path

import pytest

from tests._helpers.ast_walk import find_imports_from


class TestNoDirectModelTiersImports:
    """Verify MODEL_TIERS is not imported directly from kb.config outside config.py."""

    def test_no_direct_model_tiers_imports(self):
        """C3: No direct imports of MODEL_TIERS from kb.config in src/kb/*.

        Uses AST walk to scan all src/kb/**/*.py for ImportFrom nodes
        that import MODEL_TIERS from kb.config. Should only appear in
        src/kb/config.py itself (where it's defined/exported). This ensures
        all callers use the get_model_tier() accessor for call-time env reads.
        """
        # Explicitly exclude the versioned test files that may test
        # the old pattern (cycle 7 AC24 tests)
        excluded_files = {
            "tests/test_v099_phase39.py",
            "tests/test_v0912_phase393.py",
        }

        matches = find_imports_from(module="kb.config", name="MODEL_TIERS")
        filtered = [
            m for m in matches
            if not any(m.as_posix().endswith(excl) for excl in excluded_files)
            and "src/kb/config.py" not in str(m)
        ]

        assert not filtered, (
            f"Found direct imports of MODEL_TIERS outside config.py: {filtered}; "
            "all callers must use get_model_tier() accessor"
        )

    def test_model_tiers_bracket_access_migrated(self):
        """Verify no MODEL_TIERS[...] bracket access outside config.py."""
        # This is a more basic test that grep can catch
        import subprocess
        result = subprocess.run(
            ["grep", "-r", r"MODEL_TIERS\[", "src/kb/", "--include=*.py"],
            cwd=Path(__file__).parent.parent,
            capture_output=True,
            text=True,
        )
        # Only src/kb/config.py should have bracket access (in the accessor body)
        lines = [l for l in result.stdout.strip().split('\n') if l and 'config.py' not in l]
        assert not lines, (
            f"Found MODEL_TIERS[...] bracket access outside config.py:\n{result.stdout}; "
            "must use get_model_tier() accessor"
        )
