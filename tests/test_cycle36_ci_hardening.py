"""Cycle 36 CI hardening regression tests.

Coverage map (per Step-5 design CONDITIONS):

- C9: requires_real_api_key() helper — 4 behaviour tests covering
  unset / dummy-exact / dummy-prefix / real-prefix cases per T7 mitigation #2.
- C10: SECURITY.md ↔ workflow --ignore-vuln set-equality parsing test.
- C5/C11: skipif marker collect-only sanity (cycle-23 multiprocessing test
  remains in collection even when CI=true sets the skipif active).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from tests._helpers.api_key import requires_real_api_key

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestRequiresRealApiKey:
    """C9 — helper behaviour tests per T7 mitigation #2.

    Cycle-15 L2 / cycle-24 L4: assertions DIVERGE happy-path from buggy-path.
    A revert that always returns True (e.g., dropping the prefix check) flips
    test_dummy_exact_returns_false; a revert that always returns False (e.g.,
    swapping `bool(key) and not ...` to `bool(key) or not ...`) flips
    test_real_prefix_returns_true.
    """

    def test_unset_env_returns_false(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert requires_real_api_key() is False

    def test_dummy_exact_returns_false(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-dummy-key-for-ci-tests-only")
        assert requires_real_api_key() is False

    def test_dummy_prefix_returns_false(self, monkeypatch):
        # Any future CI key with the dummy prefix should also be rejected.
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-dummy-key-staging-2027")
        assert requires_real_api_key() is False

    def test_real_prefix_returns_true(self, monkeypatch):
        # Split-string-constructed per feedback_no_secrets_in_code so platform
        # secret scanners don't false-positive on this fixture string.
        real_looking = "sk-ant-" + "api03-real-looking-fixture-not-a-secret"
        monkeypatch.setenv("ANTHROPIC_API_KEY", real_looking)
        assert requires_real_api_key() is True

    def test_empty_string_returns_false(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "")
        assert requires_real_api_key() is False


class TestSecurityMdIgnoreVulnParity:
    """C10 — SECURITY.md advisory IDs must match workflow --ignore-vuln set 1:1.

    Cycle-32 T5 mitigation: a row in the table without a workflow flag means
    pip-audit would fail; a workflow flag without a row means silent acceptance
    (audit-trail gap). Set-equality keeps both surfaces synchronized.

    Cycle-36 Q17: Dependabot-only IDs (NOT emitted by pip-audit) belong in
    BACKLOG drift entries, NOT in SECURITY.md. This test enforces that
    invariant.
    """

    # Match the PRIMARY advisory ID per row only — the one in markdown link
    # syntax `[CVE-...](url)` or `[GHSA-...](url)`. Parenthetical alternate
    # IDs (e.g., the GHSA mirror of a CVE) appear without square brackets
    # and are documentation aids, not gate-enforced flags. Cycle-36 Q17:
    # workflow `--ignore-vuln` matches the primary IDs pip-audit emits.
    _PRIMARY_ADVISORY_RE = re.compile(
        r"\[(CVE-\d{4}-\d+|GHSA-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4})\]"
    )
    _WORKFLOW_FLAG_RE = re.compile(r"--ignore-vuln=(\S+)")

    def _security_md_ids(self) -> set[str]:
        text = (PROJECT_ROOT / "SECURITY.md").read_text(encoding="utf-8")
        # Only count IDs that appear in the "Known Advisories" rows — not in
        # the boilerplate header. Limit scan to the markdown table.
        table_section = text.split("## Known Advisories", 1)[1]
        table_section = table_section.split("## Re-check Cadence", 1)[0]
        return set(self._PRIMARY_ADVISORY_RE.findall(table_section))

    def _workflow_ignore_vuln_ids(self) -> set[str]:
        text = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        return set(self._WORKFLOW_FLAG_RE.findall(text))

    def test_security_md_ids_match_workflow_ignore_vuln(self):
        security_ids = self._security_md_ids()
        workflow_ids = self._workflow_ignore_vuln_ids()
        assert security_ids == workflow_ids, (
            f"Drift detected: SECURITY.md - workflow = {security_ids - workflow_ids}; "
            f"workflow - SECURITY.md = {workflow_ids - security_ids}. "
            f"Cycle-36 Q17: Dependabot-only IDs belong in BACKLOG, not SECURITY.md."
        )

    def test_workflow_ignore_vuln_nonempty(self):
        # Sanity: regression guard against accidentally dropping the entire
        # ignore list (would silently fail pip-audit on production CVEs).
        assert len(self._workflow_ignore_vuln_ids()) >= 4


class TestCycle23MultiprocessingSkipifMarker:
    """C5/C11 — cycle-23 multiprocessing test stays in collection.

    Cycle-36 AC2 marks the test with `skipif(os.environ.get("CI") == "true")`
    so CI runners skip it. The marker MUST NOT prevent collection — a future
    contributor reading `pytest --collect-only` should see the test name and
    can run it locally. This test asserts collection visibility, not execution.
    """

    def test_collected_in_pytest_collect_only(self):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_cycle23_file_lock_multiprocessing.py",
                "--collect-only",
                "-q",
            ],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
            env={
                **os.environ,
                "PYTHONPATH": str(PROJECT_ROOT / "src")
                + os.pathsep
                + os.environ.get("PYTHONPATH", ""),
            },
            check=False,
        )
        assert result.returncode == 0, f"pytest --collect-only failed: {result.stderr}"
        assert "test_cross_process_file_lock_timeout_then_recovery" in result.stdout, (
            f"Test not in collection: {result.stdout}"
        )


class TestPytestTimeoutInstalled:
    """C2 — pytest-timeout is installed via [dev] extras and configured.

    Cycle-36 AC3 adds the dep so any future hung test fails fast with a
    traceback instead of silently being SIGINT'd at the GHA 6-hour ceiling.
    """

    def test_pytest_timeout_importable(self):
        # Behaviour test, not a static check: confirms the dep is actually
        # installed in the venv pytest is running under.
        import importlib

        mod = importlib.import_module("pytest_timeout")
        assert mod is not None

    def test_pyproject_has_timeout_setting(self):
        # Read pyproject.toml and confirm timeout is configured. Stops a
        # silent regression where someone removes the line in [tool.pytest.
        # ini_options] without realising pytest-timeout becomes a no-op
        # default.
        text = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert "timeout = " in text, "pytest-timeout config missing from pyproject.toml"
