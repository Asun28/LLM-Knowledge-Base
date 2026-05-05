"""Cycle 65 AC2: Test no direct imports of MODEL_TIERS outside config.py (C3)."""

from pathlib import Path

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
            m
            for m in matches
            if not any(m.as_posix().endswith(excl) for excl in excluded_files)
            and "src/kb/config.py" not in str(m)
        ]

        assert not filtered, (
            f"Found direct imports of MODEL_TIERS outside config.py: {filtered}; "
            "all callers must use get_model_tier() accessor"
        )

    def test_model_tiers_bracket_access_migrated(self):
        """Verify no MODEL_TIERS[...] bracket access outside config.py."""
        repo_root = Path(__file__).resolve().parents[1]
        src_kb = repo_root / "src" / "kb"
        config_py = src_kb / "config.py"
        matches: list[str] = []

        for py_file in src_kb.rglob("*.py"):
            if py_file.resolve() == config_py.resolve():
                continue
            for lineno, line in enumerate(py_file.read_text(encoding="utf-8").splitlines(), 1):
                if "MODEL_TIERS[" in line:
                    rel_path = py_file.relative_to(repo_root).as_posix()
                    matches.append(f"{rel_path}:{lineno}: {line.strip()}")

        assert not matches, (
            "Found MODEL_TIERS[...] bracket access outside config.py:\n"
            + "\n".join(matches)
            + "\nall callers must use get_model_tier() accessor"
        )
