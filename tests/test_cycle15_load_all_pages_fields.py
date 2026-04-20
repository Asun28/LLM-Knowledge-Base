"""Cycle 15 AC32 — cycle-14 contract regression test for load_all_pages.

The production code for ``authored_by`` and ``belief_state`` additive keys
already shipped in cycle-14 AC23 (utils/pages.py:163-164). This file
serves as the machine-checked anchor: any future refactor that drops
either key from the load_all_pages dict shape fails here before merge.

Also regression-guards the cycle-14 ``status`` key.
"""

from __future__ import annotations

from pathlib import Path

from kb.utils.pages import load_all_pages


def _write_page(wiki_dir: Path, pid: str, extra_fm: str = "") -> Path:
    path = wiki_dir / "concepts" / f"{pid}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""---
title: {pid}
source:
  - raw/articles/{pid}.md
created: 2026-04-20
updated: 2026-04-20
type: concept
confidence: stated
{extra_fm}---
Body.
""",
        encoding="utf-8",
    )
    return path


def test_load_all_pages_emits_authored_by_when_present(tmp_path):
    _write_page(tmp_path, "alpha", extra_fm="authored_by: human\n")
    pages = load_all_pages(tmp_path)
    assert len(pages) == 1
    assert pages[0]["authored_by"] == "human"


def test_load_all_pages_emits_belief_state_when_present(tmp_path):
    _write_page(tmp_path, "beta", extra_fm="belief_state: confirmed\n")
    pages = load_all_pages(tmp_path)
    assert pages[0]["belief_state"] == "confirmed"


def test_load_all_pages_emits_status_when_present(tmp_path):
    """Cycle-14 AC23 regression — status key still surfaces."""
    _write_page(tmp_path, "gamma", extra_fm="status: mature\n")
    pages = load_all_pages(tmp_path)
    assert pages[0]["status"] == "mature"


def test_load_all_pages_emits_all_three_keys_when_present(tmp_path):
    """Cycle-14 L3 atomicity — all three vocabulary keys ship together."""
    _write_page(
        tmp_path,
        "complete",
        extra_fm="authored_by: hybrid\nbelief_state: uncertain\nstatus: developing\n",
    )
    pages = load_all_pages(tmp_path)
    assert pages[0]["authored_by"] == "hybrid"
    assert pages[0]["belief_state"] == "uncertain"
    assert pages[0]["status"] == "developing"


def test_load_all_pages_defaults_empty_string_when_absent(tmp_path):
    """AC32 — missing vocabulary keys default to empty string (additive shape)."""
    _write_page(tmp_path, "minimal")
    pages = load_all_pages(tmp_path)
    assert pages[0]["authored_by"] == ""
    assert pages[0]["belief_state"] == ""
    assert pages[0]["status"] == ""


def test_load_all_pages_keys_are_strings(tmp_path):
    """AC32 — additive keys are always str type (no None/list/dict leakage)."""
    _write_page(tmp_path, "types", extra_fm="authored_by: human\n")
    pages = load_all_pages(tmp_path)
    assert isinstance(pages[0]["authored_by"], str)
    assert isinstance(pages[0]["belief_state"], str)
    assert isinstance(pages[0]["status"], str)
