"""Cycle 15 AC2/AC21 — `_build_query_context` uses tier1_budget_for.

Monkeypatch `CONTEXT_TIER1_SPLIT["wiki_pages"]` and assert the tier-1
summaries budget scales proportionally. This proves the call-site
consumes the cycle-14 tier1_budget_for helper instead of bypassing it.
"""

from __future__ import annotations

from kb import config
from kb.query.engine import _build_query_context


def _summary_page(pid: str, content_chars: int) -> dict:
    return {
        "id": pid,
        "path": f"/wiki/summaries/{pid}.md",
        "title": f"Summary {pid}",
        "type": "summary",
        "confidence": "stated",
        "content": "x" * content_chars,
        "score": 1.0,
    }


def test_tier1_wiki_pages_budget_controls_summaries(monkeypatch):
    """AC21 — monkeypatching split['wiki_pages'] shrinks summaries cap proportionally."""
    # Create many 2KB summaries that would all fit at 60% split but NOT at 10%.
    pages = [_summary_page(f"s{i}", content_chars=2_000) for i in range(20)]

    # At 60% split (default), wiki_pages_budget = 20_000 * 60 / 100 = 12_000 chars.
    # A 2KB summary + header (~100 chars) = ~2100 chars; 5-6 fit into 12K.
    default_result = _build_query_context(pages)
    default_count = len(default_result["context_pages"])
    assert default_count >= 5, "default 60% split should admit at least 5 summaries"

    # Monkeypatch wiki_pages split to 10 → wiki_pages_budget = 20_000 * 10 / 100 = 2_000.
    # Only 1 summary fits (first-page truncation path).
    shrunken = dict(config.CONTEXT_TIER1_SPLIT)
    shrunken["wiki_pages"] = 10
    shrunken["chat_history"] = 20
    shrunken["index"] = 15
    shrunken["system"] = 55  # sum to 100
    monkeypatch.setattr(config, "CONTEXT_TIER1_SPLIT", shrunken)

    shrunken_result = _build_query_context(pages)
    shrunken_count = len(shrunken_result["context_pages"])
    assert shrunken_count < default_count, (
        "shrinking wiki_pages split must reduce summaries admitted; "
        f"default={default_count} shrunken={shrunken_count}"
    )


def test_tier1_budget_for_is_called(monkeypatch):
    """AC21 — _build_query_context invokes tier1_budget_for('wiki_pages').

    R1 MINOR 2 — only the engine-module alias is observable at the call site
    (``_build_query_context`` resolves ``tier1_budget_for`` from its own
    module namespace), so we patch ONLY the engine import. Patching
    ``config.tier1_budget_for`` would be redundant noise.
    """
    spy_calls: list[str] = []
    real = config.tier1_budget_for

    def _spy(component: str) -> int:
        spy_calls.append(component)
        return real(component)

    # Patch the engine's import alias so the spy is picked up.
    import kb.query.engine as engine_mod

    monkeypatch.setattr(engine_mod, "tier1_budget_for", _spy)

    pages = [_summary_page("x", content_chars=500)]
    _build_query_context(pages)
    assert "wiki_pages" in spy_calls, (
        f"expected tier1_budget_for('wiki_pages') call; got {spy_calls}"
    )
