"""Tests for Phase 4 ingest aux module fixes."""
from __future__ import annotations

import logging


def test_load_template_returns_deep_copy():
    """Mutating the returned dict must NOT corrupt the cache."""
    from kb.ingest.extractors import load_template

    a = load_template("article")
    assert isinstance(a, dict)
    # Mutate a
    a["__mutated__"] = True
    # Reload — must be a fresh dict, NOT the same object
    b = load_template("article")
    assert "__mutated__" not in b, "lru_cache is returning the same mutable dict"


def test_evidence_trail_crlf_header(tmp_path):
    """CRLF Evidence Trail header must not cause double-section append."""
    from kb.ingest.evidence import append_evidence_trail

    page = tmp_path / "p.md"
    # Write with CRLF line ending for the Evidence Trail header
    page.write_bytes(
        b"---\ntitle: p\ntype: concept\nconfidence: stated\n---\nBody\n\n## Evidence Trail\r\n\n"
    )
    append_evidence_trail(page, source_ref="raw/a.md", action="test")
    text = page.read_text(encoding="utf-8")
    count = text.count("## Evidence Trail")
    assert count == 1, f"Expected 1 Evidence Trail section, got {count}"


def test_contradiction_truncation_logged(caplog):
    """Truncating claims for contradiction check must emit a warning log.

    Phase 4.5 HIGH D5: promoted from debug to warning level.
    """
    from kb.config import CONTRADICTION_MAX_CLAIMS_TO_CHECK
    from kb.ingest.contradiction import detect_contradictions

    extra = CONTRADICTION_MAX_CLAIMS_TO_CHECK + 5
    claims = [f"claim number {i}" for i in range(extra)]
    dummy_page = {"id": "concepts/dummy", "content": "This is a dummy claim for testing."}
    with caplog.at_level(logging.WARNING, logger="kb.ingest.contradiction"):
        detect_contradictions(claims, existing_pages=[dummy_page])
    # At least one warning message about truncation
    msgs = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
    truncation_msgs = [
        m for m in msgs
        if str(CONTRADICTION_MAX_CLAIMS_TO_CHECK) in m
        or "truncat" in m.lower()
        or "first" in m.lower()
    ]
    assert truncation_msgs, f"Expected truncation warning log, got: {msgs}"
