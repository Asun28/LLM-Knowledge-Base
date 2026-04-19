"""Cycle 14 TASK 2 — optional epistemic-integrity frontmatter fields.

Covers AC2, AC3. Validates belief_state, authored_by, status fields are
backwards-compatible (absent is valid) and reject invalid values.
"""

from __future__ import annotations

import frontmatter

from kb.models.frontmatter import validate_frontmatter


def _base_metadata() -> dict:
    """Minimal metadata with all 6 required fields valid."""
    return {
        "title": "Test Page",
        "source": "raw/articles/test.md",
        "created": "2026-04-20",
        "updated": "2026-04-20",
        "type": "entity",
        "confidence": "stated",
    }


def _make_post(**extras) -> frontmatter.Post:
    md = _base_metadata()
    md.update(extras)
    post = frontmatter.Post(content="body")
    post.metadata = md
    return post


class TestOptionalFieldsAbsentBackwardsCompat:
    """AC3(a) — all three fields absent → no errors (legacy pages)."""

    def test_minimal_valid_frontmatter_no_new_errors(self):
        post = _make_post()
        assert validate_frontmatter(post) == []


class TestValidValuesAccepted:
    """AC3(b) — each field present with valid value → no error."""

    def test_belief_state_each_valid(self):
        for value in ("confirmed", "uncertain", "contradicted", "stale", "retracted"):
            post = _make_post(belief_state=value)
            assert validate_frontmatter(post) == []

    def test_authored_by_each_valid(self):
        for value in ("human", "llm", "hybrid"):
            post = _make_post(authored_by=value)
            assert validate_frontmatter(post) == []

    def test_status_each_valid(self):
        for value in ("seed", "developing", "mature", "evergreen"):
            post = _make_post(status=value)
            assert validate_frontmatter(post) == []


class TestInvalidValuesRejected:
    """AC3(c) — each field with invalid string → exactly one error."""

    def test_belief_state_invalid_string(self):
        post = _make_post(belief_state="nonsense")
        errors = validate_frontmatter(post)
        assert len(errors) == 1
        assert "belief_state" in errors[0]

    def test_authored_by_invalid_string(self):
        post = _make_post(authored_by="robot")
        errors = validate_frontmatter(post)
        assert len(errors) == 1
        assert "authored_by" in errors[0]

    def test_status_invalid_string(self):
        post = _make_post(status="bogus")
        errors = validate_frontmatter(post)
        assert len(errors) == 1
        assert "status" in errors[0]


class TestNoneAndEmptyStringRejected:
    """AC3(d) / Q17 — present field with None/empty-string → INVALID."""

    def test_belief_state_none(self):
        post = _make_post(belief_state=None)
        errors = validate_frontmatter(post)
        assert any("belief_state" in e for e in errors)

    def test_belief_state_empty_string(self):
        post = _make_post(belief_state="")
        errors = validate_frontmatter(post)
        assert any("belief_state" in e for e in errors)

    def test_authored_by_none(self):
        post = _make_post(authored_by=None)
        errors = validate_frontmatter(post)
        assert any("authored_by" in e for e in errors)

    def test_status_empty_string(self):
        post = _make_post(status="")
        errors = validate_frontmatter(post)
        assert any("status" in e for e in errors)


class TestYamlBooleanCoercionRejected:
    """AC3(e) — YAML `status: yes` coerces to True, must be rejected."""

    def test_status_true_boolean(self):
        # Simulates YAML: "status: yes" parsed to Python True.
        post = _make_post(status=True)
        errors = validate_frontmatter(post)
        assert any("status" in e for e in errors)

    def test_authored_by_false_boolean(self):
        post = _make_post(authored_by=False)
        errors = validate_frontmatter(post)
        assert any("authored_by" in e for e in errors)

    def test_belief_state_integer(self):
        post = _make_post(belief_state=1)
        errors = validate_frontmatter(post)
        assert any("belief_state" in e for e in errors)


class TestMixingValidAndInvalid:
    """Combination check — invalid+valid yields only the invalid errors."""

    def test_invalid_belief_valid_status(self):
        post = _make_post(belief_state="nope", status="mature")
        errors = validate_frontmatter(post)
        assert len(errors) == 1
        assert "belief_state" in errors[0]

    def test_all_three_invalid(self):
        post = _make_post(belief_state="a", authored_by="b", status="c")
        errors = validate_frontmatter(post)
        assert len(errors) == 3
