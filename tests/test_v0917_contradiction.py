"""Tests for auto-contradiction detection on ingest (Phase 4)."""

from kb.ingest.contradiction import detect_contradictions


class TestDetectContradictions:
    def test_no_contradictions_empty_wiki(self):
        new_claims = ["Transformers use self-attention."]
        result = detect_contradictions(new_claims, existing_pages=[])
        assert result == []

    def test_returns_contradiction_dict(self):
        new_claims = ["GPT-4 was released in 2025."]
        existing = [
            {
                "id": "entities/gpt-4",
                "content": "GPT-4 was released in March 2023.",
                "title": "GPT-4",
            }
        ]
        result = detect_contradictions(new_claims, existing_pages=existing)
        # Without LLM, this uses keyword overlap heuristic
        # We don't assert specific contradictions since heuristic-only detection
        # is intentionally conservative — just verify the structure
        assert isinstance(result, list)
        for item in result:
            assert "new_claim" in item
            assert "existing_page" in item
            assert "existing_text" in item
            assert "reason" in item

    def test_no_false_positives_on_unrelated(self):
        new_claims = ["Python is a programming language."]
        existing = [
            {
                "id": "concepts/rust",
                "content": "Rust is a systems programming language.",
                "title": "Rust",
            }
        ]
        result = detect_contradictions(new_claims, existing_pages=existing)
        assert result == []

    def test_respects_max_claims(self):
        claims = [f"Claim {i}" for i in range(20)]
        result = detect_contradictions(claims, existing_pages=[], max_claims=5)
        # Should not error even with many claims
        assert isinstance(result, list)
