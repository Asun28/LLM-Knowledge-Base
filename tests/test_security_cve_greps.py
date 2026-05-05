"""Regression tests for CVE-banned package imports (AC18)."""

import re
from pathlib import Path


class TestCVEBannedImports:
    """Assert that known-CVE packages are not imported by production code."""

    def test_diskcache_zero_imports(self):
        """Assert diskcache is never imported in src/kb/**/*.py."""
        src_kb = Path("src/kb")
        assert src_kb.exists(), "src/kb directory not found"

        # Patterns for: import diskcache and from diskcache import ...
        import_pattern = re.compile(r"^\s*(import\s+diskcache\b|from\s+diskcache\b)")

        failed_files = []
        for py_file in src_kb.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            for line_num, line in enumerate(content.splitlines(), 1):
                if import_pattern.match(line):
                    failed_files.append(f"{py_file}:{line_num}: {line.strip()}")

        assert not failed_files, "diskcache imports found:\n" + "\n".join(failed_files)

    def test_litellm_zero_imports(self):
        """Assert litellm is never imported in src/kb/**/*.py."""
        src_kb = Path("src/kb")
        assert src_kb.exists(), "src/kb directory not found"

        import_pattern = re.compile(r"^\s*(import\s+litellm\b|from\s+litellm\b)")

        failed_files = []
        for py_file in src_kb.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            for line_num, line in enumerate(content.splitlines(), 1):
                if import_pattern.match(line):
                    failed_files.append(f"{py_file}:{line_num}: {line.strip()}")

        assert not failed_files, "litellm imports found:\n" + "\n".join(failed_files)

    def test_pip_zero_imports(self):
        """Assert pip is never imported in src/kb/**/*.py."""
        src_kb = Path("src/kb")
        assert src_kb.exists(), "src/kb directory not found"

        import_pattern = re.compile(r"^\s*(import\s+pip\b|from\s+pip\b)")

        failed_files = []
        for py_file in src_kb.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            for line_num, line in enumerate(content.splitlines(), 1):
                if import_pattern.match(line):
                    failed_files.append(f"{py_file}:{line_num}: {line.strip()}")

        assert not failed_files, "pip imports found:\n" + "\n".join(failed_files)

    def test_ragas_zero_imports(self):
        """Assert ragas is never imported in src/kb/**/*.py."""
        src_kb = Path("src/kb")
        assert src_kb.exists(), "src/kb directory not found"

        import_pattern = re.compile(r"^\s*(import\s+ragas\b|from\s+ragas\b)")

        failed_files = []
        for py_file in src_kb.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            for line_num, line in enumerate(content.splitlines(), 1):
                if import_pattern.match(line):
                    failed_files.append(f"{py_file}:{line_num}: {line.strip()}")

        assert not failed_files, "ragas imports found:\n" + "\n".join(failed_files)
