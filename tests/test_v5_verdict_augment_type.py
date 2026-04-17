"""Regression: VALID_VERDICT_TYPES includes 'augment' for kb_lint --augment verdicts."""

import json

from kb.lint.verdicts import VALID_VERDICT_TYPES, add_verdict
from kb.utils.io import atomic_json_write


def test_augment_is_a_valid_verdict_type():
    assert "augment" in VALID_VERDICT_TYPES


def test_add_verdict_accepts_augment_type(tmp_path, monkeypatch):
    verdicts_path = tmp_path / "verdicts.json"
    monkeypatch.setattr("kb.lint.verdicts.VERDICTS_PATH", verdicts_path)
    atomic_json_write([], verdicts_path)

    add_verdict(
        page_id="concepts/mixture-of-experts",
        verdict_type="augment",
        verdict="pass",
        notes="augmented from wikipedia, body 1.2k chars, 1 citation",
        issues=[],
    )
    saved = json.loads(verdicts_path.read_text())
    assert any(v["verdict_type"] == "augment" for v in saved)


def test_add_verdict_rejects_unknown_type(tmp_path, monkeypatch):
    import pytest

    verdicts_path = tmp_path / "verdicts.json"
    monkeypatch.setattr("kb.lint.verdicts.VERDICTS_PATH", verdicts_path)
    atomic_json_write([], verdicts_path)

    with pytest.raises(ValueError, match="Invalid verdict_type"):
        add_verdict(
            page_id="concepts/foo",
            verdict_type="not_a_real_type",
            verdict="pass",
            notes="x",
            issues=[],
        )
