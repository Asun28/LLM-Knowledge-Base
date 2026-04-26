"""Cycle 34 — Release hygiene regression tests.

Fixture-free per R2 cycle-19 L2 safety (no module-top reads triggered by
``importlib.reload`` siblings). Each test parses the on-disk file directly
or imports a stable static-frozenset.

ACs covered: AC37-AC48 (original test set) + AC51-AC57 (added at Step 5).
AC55 (architecture-diagram version regression) is intentionally deferred per
the cycle-34 design's NEW-Q15 fallback — diagrams stay at v0.10.0 until cycle
35; BACKLOG entry tracks the follow-up.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_pyproject() -> dict:
    return tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────
# pyproject.toml
# ─────────────────────────────────────────────────────────────────────


def test_pyproject_readme_is_readme_md():
    """AC37: pyproject readme points at README.md, not CLAUDE.md (Finding 3)."""
    proj = _load_pyproject()["project"]
    assert proj["readme"] == "README.md", (
        f"pyproject.toml [project].readme must be 'README.md', got {proj['readme']!r}"
    )


def test_pyproject_has_required_extras():
    """AC38: 5 optional-dependency keys declared with non-empty pin lists."""
    proj = _load_pyproject()["project"]
    extras = proj["optional-dependencies"]
    expected_keys = {"hybrid", "augment", "formats", "eval", "dev"}
    assert expected_keys <= set(extras.keys()), (
        f"missing extras: {expected_keys - set(extras.keys())}"
    )
    for key in expected_keys:
        assert isinstance(extras[key], list) and len(extras[key]) >= 1, (
            f"extra {key!r} must be a non-empty list, got {extras[key]!r}"
        )


def test_pyproject_runtime_deps_include_jsonschema_and_anthropic():
    """AC39: runtime dependencies include jsonschema (cycle 34 fix) and anthropic (Q1 KEEP)."""
    deps = _load_pyproject()["project"]["dependencies"]
    dep_names = {
        d.split(">")[0].split("=")[0].split("<")[0].split("[")[0].strip().lower() for d in deps
    }
    assert "jsonschema" in dep_names, f"jsonschema missing from runtime deps: {deps}"
    assert "anthropic" in dep_names, f"anthropic must remain required (Q1): {deps}"


def test_pyproject_version_is_0_11_0():
    """AC52: cycle-34 minor bump 0.10.0 → 0.11.0 (NEW-Q11 / AC4a)."""
    version = _load_pyproject()["project"]["version"]
    assert version == "0.11.0", f"expected 0.11.0, got {version!r}"


# ─────────────────────────────────────────────────────────────────────
# src/kb/__init__.py — version lockstep
# ─────────────────────────────────────────────────────────────────────


def test_kb_init_version_matches_pyproject():
    """AC53: src/kb/__init__.py.__version__ MUST match pyproject (NEW-Q11 / AC4b).

    Cycle-21 audit explicitly aligned these after they drifted; this test pins
    the alignment.
    """
    import kb

    assert kb.__version__ == "0.11.0", f"kb.__version__ is {kb.__version__!r}, expected 0.11.0"
    pyproject_version = _load_pyproject()["project"]["version"]
    assert kb.__version__ == pyproject_version, (
        f"kb.__version__ ({kb.__version__!r}) drifted from pyproject ({pyproject_version!r})"
    )


# ─────────────────────────────────────────────────────────────────────
# README.md
# ─────────────────────────────────────────────────────────────────────


def test_no_vectors_tagline_absent():
    """AC40: README.md must NOT contain literal 'No vectors. No chunking.' (Finding 5)."""
    body = _read("README.md")
    assert "No vectors. No chunking." not in body, (
        "AC18 replaced this misleading tagline; revert would re-introduce contract drift"
    )


def test_kb_save_synthesis_absent_from_readme():
    """AC51 (forward regression for AC22): kb_save_synthesis must not appear in README.md.

    The implementation has always been kb_query(save_as=...); kb_save_synthesis was
    only ever a doc-rename target. This forward-regression catches any future cycle
    that re-introduces the misleading reference.
    """
    body = _read("README.md")
    assert "kb_save_synthesis" not in body, (
        "AC22 verified kb_save_synthesis already absent from README; revert/re-introduction blocked"
    )


def test_readme_version_badge_is_v0_11_0():
    """AC54: README.md version badge updated to v0.11.0 (NEW-Q11 / AC4c)."""
    body = _read("README.md")
    assert "version-v0.11.0-orange" in body, "version badge URL must show v0.11.0"
    # Forward regression: stale v0.10.0 badge would re-introduce Finding 6 drift class.
    assert "version-v0.10.0-orange" not in body, "stale v0.10.0 badge must be removed"


# ─────────────────────────────────────────────────────────────────────
# src/kb/config.py
# ─────────────────────────────────────────────────────────────────────


def test_pdf_not_in_supported_extensions():
    """AC41: .pdf removed from SUPPORTED_SOURCE_EXTENSIONS (Finding 7 / AC24).

    Per R2 verification, kb.config has no module-top reads of WIKI_DIR/RAW_DIR
    so this fixture-free import is reload-leak safe.
    """
    from kb.config import SUPPORTED_SOURCE_EXTENSIONS

    assert ".pdf" not in SUPPORTED_SOURCE_EXTENSIONS, (
        f"cycle 34 AC24 removed .pdf; revert would re-introduce Finding 7 drift: "
        f"{sorted(SUPPORTED_SOURCE_EXTENSIONS)}"
    )
    # Sanity: still has expected text formats
    for ext in {".md", ".txt", ".json", ".yaml", ".yml", ".rst", ".csv"}:
        assert ext in SUPPORTED_SOURCE_EXTENSIONS, f"{ext} must remain supported"


# ─────────────────────────────────────────────────────────────────────
# Filesystem deletes (T7 mitigation)
# ─────────────────────────────────────────────────────────────────────


def test_scratch_files_absent():
    """AC42: 4 root-level scratch files deleted (Finding 9)."""
    for path in ("findings.md", "progress.md", "task_plan.md", "claude4.6.md"):
        assert not (REPO_ROOT / path).exists(), (
            f"{path} must be deleted (cycle 34 AC29-AC32); "
            f"revert re-introduces Finding 9 hygiene gap"
        )


def test_old_repo_review_files_deleted():
    """AC47: superseded docs/repo_review.{md,html} deleted (AC33-AC34)."""
    assert not (REPO_ROOT / "docs" / "repo_review.md").exists(), (
        "docs/repo_review.md was superseded by docs/reviews/2026-04-25-comprehensive-repo-review.md"
    )
    assert not (REPO_ROOT / "docs" / "repo_review.html").exists(), (
        "docs/repo_review.html was superseded by the dated review under docs/reviews/"
    )


# ─────────────────────────────────────────────────────────────────────
# .gitignore
# ─────────────────────────────────────────────────────────────────────


def test_gitignore_lists_scratch_patterns():
    """AC43: .gitignore covers cycle-34 scratch patterns (T7 mitigation)."""
    body = _read(".gitignore")
    # Existing patterns (already present pre-cycle-34, regression-only)
    for pattern in ("/findings.md", "/progress.md", "/task_plan.md", "claude4.6.md"):
        assert pattern in body, f".gitignore must list {pattern!r}"
    # New forward-looking pattern (cycle 34 AC17)
    assert "cycle-*-scratch/" in body, (
        ".gitignore must include forward-looking cycle-*-scratch/ pattern"
    )


# ─────────────────────────────────────────────────────────────────────
# SECURITY.md
# ─────────────────────────────────────────────────────────────────────


def test_security_md_has_required_sections():
    """AC44: SECURITY.md exists with three required H2 sections."""
    body = _read("SECURITY.md")
    # Use prefix-match (regex-tolerant per R2) — accept the headers in any
    # reasonable form
    for header in ("## Vulnerability Reporting", "## Known Advisories", "## Re-check Cadence"):
        assert header in body, f"SECURITY.md missing header: {header!r}"
    # Each of the 4 narrow-role advisories listed
    for cve_id in ("CVE-2025-69872", "GHSA-xqmj-j6mv-4862", "CVE-2026-3219", "CVE-2026-6587"):
        assert cve_id in body, f"SECURITY.md must document advisory {cve_id}"


# ─────────────────────────────────────────────────────────────────────
# .github/workflows/ci.yml
# ─────────────────────────────────────────────────────────────────────


def test_ci_workflow_yaml_parses():
    """AC45: CI workflow exists, parses, has all required structure.

    Per R2 NEW-Q18: explicit permissions: read-all (T1).
    Per NEW-Q16: on: push: branches: [main], pull_request: {} (NT4).
    Per NEW-Q23: concurrency: cancel-in-progress: true (NT5).
    Per AC50: dedicated `pip install build twine pip-audit` step.
    Per AC14: pip-audit -r requirements.txt with 4 ignore-vuln IDs.
    Per Step-6 amendment: actions use @v6 (not @v4/@v5).
    """
    workflow_path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    assert workflow_path.exists(), "cycle 34 AC9 requires .github/workflows/ci.yml"

    raw = workflow_path.read_text(encoding="utf-8")
    parsed = yaml.safe_load(raw)

    # `on:` is a YAML reserved word that PyYAML sometimes parses as bool True;
    # we check both forms
    on_block = parsed.get("on") or parsed.get(True)
    assert on_block is not None, "workflow must have an `on:` trigger block"
    assert "push" in on_block and "pull_request" in on_block, "must trigger on push + pull_request"
    push_block = on_block["push"]
    if isinstance(push_block, dict):
        assert push_block.get("branches") == ["main"], (
            f"push trigger must be narrowed to main only (NT4): {push_block!r}"
        )

    # T1: explicit permissions block (read-all or contents: read)
    perms = parsed.get("permissions")
    assert perms is not None, "workflow must declare top-level permissions: block (T1)"
    assert perms == "read-all" or (isinstance(perms, dict) and "write" not in str(perms).lower()), (
        f"permissions must be read-all or read-only (T1): {perms!r}"
    )

    # NT5: concurrency block
    conc = parsed.get("concurrency")
    assert conc is not None, "workflow must declare concurrency block (NT5)"
    assert "cancel-in-progress" in str(conc), "concurrency must include cancel-in-progress"

    # T1: no secrets.* references; no pull_request_target trigger.
    # Parse-aware checks (raw string-grep would false-positive on documentation
    # comments that say "NOT pull_request_target" — see Step-9 fix when this
    # test failed on a comment in ci.yml describing the threat-model decision).
    assert "pull_request_target" not in on_block, "must NOT use pull_request_target trigger (T1)"
    # secrets.X references appear as ${{ secrets.NAME }} in YAML run steps; we
    # check the run lines specifically rather than the comment text
    for job in parsed.get("jobs", {}).values():
        for step in job.get("steps", []):
            run_text = step.get("run", "")
            assert "${{ secrets." not in run_text, (
                f"step {step.get('name')!r} references secrets.* (T1)"
            )

    # AC50: dedicated CI tooling install step
    assert "pip install build twine pip-audit" in raw, "AC50 dedicated install step missing"

    # AC14: pip-audit invocation with 4 ignore-vuln flags
    for cve_id in ("CVE-2025-69872", "GHSA-xqmj-j6mv-4862", "CVE-2026-3219", "CVE-2026-6587"):
        assert cve_id in raw, f"pip-audit must ignore {cve_id} (T4 mitigation)"

    # T2 amendment: actions/checkout@v6 + actions/setup-python@v6 (not @v4/@v5)
    assert "actions/checkout@v6" in raw, "Step-6 amendment: bump checkout to @v6"
    assert "actions/setup-python@v6" in raw, "Step-6 amendment: bump setup-python to @v6"


def test_pip_audit_invocation_audits_live_env():
    """AC57 (cycle-34 fix-after-CI-failure-4 regression): pip-audit audits the LIVE env.

    Cycle-22 L1 documented that `pip-audit -r requirements.txt` trips
    ResolutionImpossible on pre-existing conflicts.  Cycle-34's first attempt
    added `--no-deps` to suppress that — but pip-audit's `--no-deps` flag
    only suppresses ITS OWN transitive auditing; the underlying
    `pip install --dry-run` resolution step still runs and still fails.

    Fix: audit the LIVE installed environment (no `-r` flag).  Since the
    previous CI step installs every extra (`[dev,formats,augment,hybrid,
    eval]`), the live env IS the audit surface — coverage is equivalent to
    auditing requirements.txt, but pip-audit walks `pip list` instead of
    spinning up a fresh venv install that fails resolution.
    """
    raw = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    audit_step_idx = raw.find("pip-audit `")
    assert audit_step_idx >= 0, "pip-audit invocation not found"
    audit_step_end = raw.find("\n\n", audit_step_idx)
    audit_step = raw[
        audit_step_idx : audit_step_end if audit_step_end > 0 else audit_step_idx + 500
    ]
    # Cycle-34 fix-after-CI-failure-4: must NOT use `-r requirements.txt`
    assert "-r requirements.txt" not in audit_step, (
        f"pip-audit must audit live env, not requirements.txt (cycle-22 L1 trap); "
        f"audit step: {audit_step!r}"
    )
    # Must still carry all 4 ignore-vuln flags
    for cve in ("CVE-2025-69872", "GHSA-xqmj-j6mv-4862", "CVE-2026-3219", "CVE-2026-6587"):
        assert cve in audit_step, f"pip-audit step missing {cve} ignore"


# ─────────────────────────────────────────────────────────────────────
# CLAUDE.md
# ─────────────────────────────────────────────────────────────────────


def test_kb_save_synthesis_clarification_in_claude_md():
    """AC46 (positive regression for AC27): docs use save_as= correctly.

    Cycle 35: CLAUDE.md split into docs/reference/* (commit 518db0e). The
    save_as= clarification moved to docs/reference/mcp-servers.md (the
    Tool Catalogue section). The forward regression — kb_save_synthesis must
    not be re-introduced as an MCP tool — applies to BOTH files.
    """
    mcp_servers_body = _read("docs/reference/mcp-servers.md")
    claude_md_body = _read("CLAUDE.md")
    assert "save_as=" in mcp_servers_body, (
        "docs/reference/mcp-servers.md must use save_as= form (AC27 verified)"
    )
    # Forward regression — kb_save_synthesis appears nowhere in either file.
    assert "kb_save_synthesis" not in mcp_servers_body, (
        "mcp-servers.md must NOT mention kb_save_synthesis (it was never an MCP tool)"
    )
    assert "kb_save_synthesis" not in claude_md_body, (
        "CLAUDE.md must NOT mention kb_save_synthesis (it was never an MCP tool)"
    )


# ─────────────────────────────────────────────────────────────────────
# docs/reviews/
# ─────────────────────────────────────────────────────────────────────


def test_comprehensive_review_present():
    """AC48: 2026-04-25 comprehensive review committed at docs/reviews/.

    Uses prefix-match + substring check per R2 robustness against em-dash drift.
    """
    review_path = REPO_ROOT / "docs" / "reviews" / "2026-04-25-comprehensive-repo-review.md"
    assert review_path.exists(), "AC35: cycle 34 must commit the comprehensive review"

    first_line = review_path.read_text(encoding="utf-8").split("\n", 1)[0]
    # Prefix match (no em-dash dependency)
    assert first_line.startswith("# LLM Wiki Flywheel"), (
        f"first line must start with the project name; got {first_line!r}"
    )
    # Substring: confirms it's the comprehensive review specifically
    assert "Comprehensive Repository Review" in first_line, (
        f"first line must identify as the comprehensive review; got {first_line!r}"
    )


# ─────────────────────────────────────────────────────────────────────
# Boot-lean (NEW-Q14 / AC56)
# ─────────────────────────────────────────────────────────────────────


def test_boot_lean_minimal_install():
    """AC56 (forward regression for NEW-Q14): kb.cli imports cleanly with default deps only.

    Per cycle 34 Step 9 verification: kb.cli does NOT pull in kb.lint.fetcher,
    httpx, httpcore, or trafilatura at module-load time. AC49 production fix was
    DROPPED at Step 9 because the import chain was already function-local.
    This test pins the contract so any future cycle that introduces a module-top
    fetcher import (regressing the boot-lean state) is caught.

    Per cycle-7 L4: subprocess tests need explicit PYTHONPATH or cwd.
    """
    src_dir = REPO_ROOT / "src"
    env = {
        **os.environ,
        "PYTHONPATH": str(src_dir) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    probe = (
        "import sys; "
        "before = set(sys.modules); "
        "import kb.cli; "
        "from kb.cli import cli; "
        "loaded = sorted(set(sys.modules) - before); "
        "leaks = [m for m in loaded if m in ('httpx', 'httpcore', 'trafilatura') "
        "         or m.startswith('kb.lint.fetcher')]; "
        "print('LEAKS:', leaks); "
        "sys.exit(0 if not leaks else 1)"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
        timeout=30,
    )
    assert result.returncode == 0, (
        f"boot-lean regression — kb.cli pulls in extras-only modules at import time.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "LEAKS: []" in result.stdout, (
        f"unexpected modules loaded by kb.cli boot:\n{result.stdout}"
    )
