"""Cycle 68 AC12 — lint_yaml loader safety + fallback + call-time read pins.

TDD red→green pin for ``kb.lint._lint_yaml.load_lint_config`` (added by AC03).
Six pins:

1. ``yaml.safe_load`` ONLY (FW-2 / RCE class T7) — malicious payload via
   ``!!python/object/new:os.system [...]`` MUST NOT execute side effects.
2. Missing file → return ``{}`` (graceful fallback).
3. Malformed YAML → return ``{}`` + warning (no crash).
4. POSIX permission error → return ``{}`` + warning (no crash).
5. Schema validation: ``duplicate_slug_allowlist`` MUST be a list-of-pairs;
   wrong shape → warning + key dropped (key falls through to defaults).
6. Call-time read: rewriting the file BETWEEN calls returns the new value
   (cycle-19 L2 no-cache contract).
"""

from __future__ import annotations

import logging
import os
import stat
import sys
from pathlib import Path

import pytest


def test_lint_yaml_rejects_malicious_payload(
    tmp_kb_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC12 / FW-2 — malicious yaml.load tag MUST NOT execute (yaml.safe_load only)."""
    from kb.lint._lint_yaml import load_lint_config

    wiki_dir = tmp_kb_env / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    # Classic yaml.load RCE payload — !!python/object/new constructs Python objects
    # that yaml.safe_load REFUSES (raises ConstructorError); yaml.load would execute.
    payload = "!!python/object/new:os.system [\"echo PWNED > pwned.txt\"]\n"
    (wiki_dir / "_lint.yml").write_text(payload, encoding="utf-8")

    invocations: list[tuple] = []
    real_system = os.system

    def spy_system(*args, **kwargs):
        invocations.append((args, kwargs))
        return real_system(*args, **kwargs)

    monkeypatch.setattr(os, "system", spy_system)

    result = load_lint_config(wiki_dir=wiki_dir)

    # FW-2 pin: malicious payload MUST NOT have invoked os.system AND MUST return {}.
    assert invocations == [], (
        f"yaml.load RCE payload triggered os.system: {invocations!r} — "
        "loader is using yaml.load instead of yaml.safe_load (FW-2 violation)"
    )
    assert result == {}, f"Malicious payload should yield empty dict, got {result!r}"
    # Defensive: pwned.txt MUST NOT exist (in case spy bypass).
    assert not (wiki_dir / "pwned.txt").exists(), "RCE side-effect file appeared"


def test_lint_yaml_file_missing_returns_empty(tmp_kb_env: Path) -> None:
    """AC12 — missing _lint.yml returns {} (graceful fallback, no exception)."""
    from kb.lint._lint_yaml import load_lint_config

    wiki_dir = tmp_kb_env / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    # Confirm file absent.
    assert not (wiki_dir / "_lint.yml").exists()

    result = load_lint_config(wiki_dir=wiki_dir)
    assert result == {}, f"Missing file should yield empty dict, got {result!r}"


def test_lint_yaml_parse_error_returns_empty(
    tmp_kb_env: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """AC12 — malformed YAML returns {} AND emits a warning (no crash)."""
    from kb.lint._lint_yaml import load_lint_config

    wiki_dir = tmp_kb_env / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    # Unbalanced bracket → yaml.YAMLError on safe_load.
    (wiki_dir / "_lint.yml").write_text("[unbalanced: bracket\n", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="kb.lint._lint_yaml"):
        result = load_lint_config(wiki_dir=wiki_dir)

    assert result == {}, f"Malformed YAML should yield empty dict, got {result!r}"
    assert any(
        "YAML" in rec.getMessage() or "parse" in rec.getMessage()
        for rec in caplog.records
    ), (
        f"Expected YAML parse warning; got records: "
        f"{[r.getMessage() for r in caplog.records]!r}"
    )


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX-only: chmod 000 does not block reads on Windows ACL model",
)
def test_lint_yaml_io_permission_returns_empty(
    tmp_kb_env: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """AC12 — POSIX permission error returns {} + warning (graceful)."""
    from kb.lint._lint_yaml import load_lint_config

    wiki_dir = tmp_kb_env / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    target = wiki_dir / "_lint.yml"
    target.write_text("ok: 1\n", encoding="utf-8")
    # chmod 000 — read returns OSError (PermissionError).
    target.chmod(0o000)
    try:
        with caplog.at_level(logging.WARNING, logger="kb.lint._lint_yaml"):
            result = load_lint_config(wiki_dir=wiki_dir)
        assert result == {}, (
            f"Permission error should yield empty dict, got {result!r}"
        )
        assert any(
            "read" in rec.getMessage().lower() or "error" in rec.getMessage().lower()
            for rec in caplog.records
        ), (
            f"Expected read-error warning; got: "
            f"{[r.getMessage() for r in caplog.records]!r}"
        )
    finally:
        # Restore perms so pytest can clean up.
        target.chmod(stat.S_IRUSR | stat.S_IWUSR)


def test_lint_yaml_schema_mixed_type_warning(
    tmp_kb_env: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """AC12 — wrong-shape duplicate_slug_allowlist warns + key drops."""
    from kb.lint._lint_yaml import load_lint_config

    wiki_dir = tmp_kb_env / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    # duplicate_slug_allowlist must be list-of-2-element-lists; string is wrong shape.
    (wiki_dir / "_lint.yml").write_text(
        "duplicate_slug_allowlist: not-a-list\nother_key: keep_me\n",
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING, logger="kb.lint._lint_yaml"):
        result = load_lint_config(wiki_dir=wiki_dir)

    # Bad key MUST be dropped; sibling keys MUST survive (overlay falls through to defaults).
    assert "duplicate_slug_allowlist" not in result, (
        f"Wrong-shape duplicate_slug_allowlist should be dropped; got {result!r}"
    )
    assert result.get("other_key") == "keep_me", (
        f"Sibling keys should survive; got {result!r}"
    )
    assert any(
        "duplicate_slug_allowlist" in rec.getMessage() for rec in caplog.records
    ), (
        f"Expected schema warning; got: "
        f"{[r.getMessage() for r in caplog.records]!r}"
    )


def test_lint_yaml_call_time_read(tmp_kb_env: Path) -> None:
    """AC12 — file rewrite BETWEEN calls reflects on second read (cycle-19 L2 no-cache)."""
    from kb.lint._lint_yaml import load_lint_config

    wiki_dir = tmp_kb_env / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    target = wiki_dir / "_lint.yml"

    # First write → first read.
    target.write_text("phase: A\n", encoding="utf-8")
    first = load_lint_config(wiki_dir=wiki_dir)
    assert first.get("phase") == "A", f"First read mismatch: {first!r}"

    # Rewrite to phase B.
    target.write_text("phase: B\n", encoding="utf-8")
    second = load_lint_config(wiki_dir=wiki_dir)
    assert second.get("phase") == "B", (
        f"Second read should reflect new value; loader is module-caching "
        f"(cycle-19 L2 violation). Got {second!r}"
    )
