"""Regression tests for CVE-banned package imports (AC18)."""

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _requirement_name(requirement: str) -> str:
    return (
        re.split(r"\s*(?:==|>=|<=|~=|!=|<|>|;|\[)", requirement, maxsplit=1)[0]
        .strip()
        .lower()
    )


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


class TestDependabotAlertManifests:
    """Assert removed Dependabot-alerted package names stay out of install manifests."""

    def test_litellm_and_ragas_absent_from_install_manifests(self):
        blocked = {"litellm", "ragas"}

        pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        project = pyproject["project"]
        manifest_requirements: list[tuple[str, str]] = [
            ("pyproject.toml [project.dependencies]", dep)
            for dep in project.get("dependencies", [])
        ]
        for extra_name, deps in project.get("optional-dependencies", {}).items():
            manifest_requirements.extend(
                (f"pyproject.toml [project.optional-dependencies.{extra_name}]", dep)
                for dep in deps
            )

        for line in (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("-"):
                continue
            manifest_requirements.append(("requirements.txt", stripped))

        found = [
            f"{source}: {requirement}"
            for source, requirement in manifest_requirements
            if _requirement_name(requirement) in blocked
        ]

        assert not found, "Dependabot-alerted packages must stay removed:\n" + "\n".join(found)
