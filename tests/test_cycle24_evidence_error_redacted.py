"""Cycle 24 AC2/AC4 — StorageError redaction for evidence-append failures.

When `_update_existing_page` fails at `append_evidence_trail`, the failure
must surface as a typed `StorageError(kind="evidence_trail_append_failure")`
with path redacted per the cycle-20 error taxonomy contract.

Late-binds `StorageError` via `pipeline_mod.StorageError` per cycle-20 L1 rule
(reload-leak makes `pytest.raises(CLS)` misfire when importing from
`kb.errors` directly).

Closes threat T6 + CONDITION 12 from `2026-04-23-cycle24-design.md`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kb.ingest import pipeline as pipeline_mod


def test_update_existing_page_evidence_oserror_raises_redacted_storage_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC4 — `_update_existing_page` must surface evidence-append OSError as
    `StorageError(kind="evidence_trail_append_failure", path=page_path)` with
    `str(err)` redacting the path to `<path_hidden>` per cycle-20 contract.
    """
    # Seed an existing page with frontmatter + body. The body must NOT already
    # reference the new source_ref in its YAML `source:` list, otherwise
    # `_update_existing_page_body` returns False (page_wrote=False) and the
    # AC2 evidence-append branch never fires.
    page = tmp_path / "existing.md"
    page.write_text(
        "---\n"
        "title: Existing Page\n"
        "source:\n"
        "  - raw/articles/original.md\n"
        "created: 2026-01-01\n"
        "updated: 2026-01-01\n"
        "type: entity\n"
        "confidence: stated\n"
        "---\n\n"
        "# Existing Page\n\n"
        "Pre-existing body content.\n",
        encoding="utf-8",
    )

    # Force `append_evidence_trail` to raise OSError — the AC2 try/except MUST
    # translate that into the typed StorageError.
    def _raise_oserror(*args, **kwargs):
        raise OSError("simulated disk-full during evidence append")

    monkeypatch.setattr(pipeline_mod, "append_evidence_trail", _raise_oserror)

    # Late-bind StorageError via pipeline module to dodge reload-drift
    # (cycle-20 L1: `pytest.raises(CLS)` misfires when the test-module import
    # is bound pre-reload but the production module points at a post-reload
    # class object).
    StorageError = pipeline_mod.StorageError

    with pytest.raises(StorageError) as excinfo:
        pipeline_mod._update_existing_page(
            page_path=page,
            source_ref="raw/articles/new.md",
            name="Thing",
            verb="Mentioned",
        )

    # Kind field pins the failure taxonomy (cycle-20 contract).
    assert excinfo.value.kind == "evidence_trail_append_failure", (
        f"Expected kind='evidence_trail_append_failure'; got {excinfo.value.kind!r}"
    )

    # Path redaction pinned (cycle-20 __str__ contract).
    assert str(excinfo.value) == "evidence_trail_append_failure: <path_hidden>", (
        f"Expected redacted form; got {str(excinfo.value)!r}"
    )

    # __cause__ chain preserves the original OSError for debugging.
    assert isinstance(excinfo.value.__cause__, OSError)
    assert "simulated disk-full" in str(excinfo.value.__cause__)


def test_update_existing_page_non_oserror_propagates_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC2 explicit non-goal: non-OSError exceptions from `append_evidence_trail`
    propagate WITHOUT being wrapped in StorageError. This preserves the
    cycle-20 taxonomy coverage scope (StorageError is for filesystem/audit-write
    failures; other exception classes are their own taxonomy items).
    """
    page = tmp_path / "existing.md"
    page.write_text(
        "---\n"
        "title: Existing Page\n"
        "source:\n"
        "  - raw/articles/original.md\n"
        "created: 2026-01-01\n"
        "updated: 2026-01-01\n"
        "type: entity\n"
        "confidence: stated\n"
        "---\n\n"
        "# Existing Page\n\n"
        "Body.\n",
        encoding="utf-8",
    )

    def _raise_value_error(*args, **kwargs):
        raise ValueError("programmer error, not a storage failure")

    monkeypatch.setattr(pipeline_mod, "append_evidence_trail", _raise_value_error)

    # ValueError propagates unchanged — NOT wrapped in StorageError.
    with pytest.raises(ValueError, match="programmer error"):
        pipeline_mod._update_existing_page(
            page_path=page,
            source_ref="raw/articles/new.md",
            name="Thing",
            verb="Mentioned",
        )
