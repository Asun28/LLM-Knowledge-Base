"""Regression tests for CVE-banned package imports (AC18; cycle-66 AC4 refactor)."""

import re
import tomllib
from pathlib import Path

import pytest

from tests._helpers.ast_walk import find_module_imports

REPO_ROOT = Path(__file__).resolve().parents[1]

# Modules removed from the project under prior CVE-driven dependency repairs.
# The helper detects BOTH bare-form (`import M`) and from-form (`from M import X`)
# plus namespace prefixes (`import M.sub`). Cycle-66 AC4 / T6 closure.
CVE_BANNED_MODULES = ["diskcache", "litellm", "pip", "ragas"]


def _requirement_name(requirement: str) -> str:
    return re.split(r"\s*(?:==|>=|<=|~=|!=|<|>|;|\[)", requirement, maxsplit=1)[0].strip().lower()


class TestCVEBannedImports:
    """Assert that known-CVE packages are not imported by production code."""

    @pytest.mark.parametrize("module", CVE_BANNED_MODULES)
    def test_module_zero_imports(self, module):
        """Assert `module` is never imported in src/kb/**/*.py (bare or from form)."""
        src_kb = Path("src/kb")
        assert src_kb.exists(), "src/kb directory not found"

        result = find_module_imports(module, src_root=src_kb)
        all_hits = sorted(set(result["import"]) | set(result["from"]))
        assert not all_hits, f"{module} imports found in production code:\n" + "\n".join(
            str(p) for p in all_hits
        )


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
