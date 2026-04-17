"""Tests for auto-contradiction detection on ingest (Phase 4)."""

from kb.ingest.contradiction import detect_contradictions


class TestDetectContradictions:
    def test_no_contradictions_empty_wiki(self):
        new_claims = ["Transformers use self-attention."]
        result = detect_contradictions(new_claims, existing_pages=[])
        assert result == []

    def test_no_false_positives_on_unrelated(self):
        # Use genuinely disjoint vocabularies to prevent heuristic false-positives.
        new_claims = ["The Eiffel Tower stands in Paris."]
        existing = [
            {
                "id": "concepts/qcd",
                "content": "Quantum chromodynamics describes quark interactions.",
                "title": "QCD",
            }
        ]
        result = detect_contradictions(new_claims, existing_pages=existing)
        assert result == []

    def test_respects_max_claims(self):
        claims = [f"Claim {i}" for i in range(20)]
        result = detect_contradictions(claims, existing_pages=[], max_claims=5)
        # Should not error even with many claims
        assert isinstance(result, list)


def test_returns_empty_list_when_no_contradiction(tmp_project):
    """Regression: Phase 4.5 CRITICAL item 2 (empty-path explicitly tested, no silent loop-skip)."""
    from kb.ingest.contradiction import detect_contradictions

    result = detect_contradictions(new_claims=["unrelated topic"], existing_pages=[])
    assert result == []


def test_returns_contradiction_dict_when_heuristic_fires(tmp_project):
    """Regression: Phase 4.5 CRITICAL item 2 (fired path: verify dict shape)."""
    from kb.ingest.contradiction import detect_contradictions

    existing_pages = [
        {
            "id": "concepts/latency",
            "content": "Network latency is always high in mobile networks.",
        }
    ]
    result = detect_contradictions(
        new_claims=["Network latency is never high in mobile networks."],
        existing_pages=existing_pages,
    )
    assert len(result) >= 1, "heuristic should catch 'always' vs 'never'"
    item = result[0]
    for key in ("new_claim", "existing_page", "existing_text", "reason"):
        assert key in item
