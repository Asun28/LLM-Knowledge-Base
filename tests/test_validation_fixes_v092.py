"""Tests for v0.9.2 validation fixes — feedback input, verdict severity, refiner frontmatter."""

import pytest

# --- Feedback input validation tests ---


def test_feedback_question_too_long(tmp_path):
    from kb.feedback.store import add_feedback_entry

    feedback_file = tmp_path / "feedback.json"
    with pytest.raises(ValueError, match="Question too long"):
        add_feedback_entry("x" * 3000, "useful", [], path=feedback_file)


def test_feedback_notes_too_long(tmp_path):
    from kb.feedback.store import add_feedback_entry

    feedback_file = tmp_path / "feedback.json"
    with pytest.raises(ValueError, match="Notes too long"):
        add_feedback_entry("valid question", "useful", [], notes="n" * 3000, path=feedback_file)


def test_feedback_too_many_cited_pages(tmp_path):
    from kb.feedback.store import add_feedback_entry

    feedback_file = tmp_path / "feedback.json"
    pages = [f"concepts/page-{i}" for i in range(60)]
    with pytest.raises(ValueError, match="Too many cited pages"):
        add_feedback_entry("valid question", "useful", pages, path=feedback_file)


def test_feedback_page_id_traversal(tmp_path):
    from kb.feedback.store import add_feedback_entry

    feedback_file = tmp_path / "feedback.json"
    with pytest.raises(ValueError, match="Invalid page ID"):
        add_feedback_entry("valid question", "useful", ["../etc/passwd"], path=feedback_file)


def test_feedback_page_id_too_long(tmp_path):
    from kb.feedback.store import add_feedback_entry

    feedback_file = tmp_path / "feedback.json"
    with pytest.raises(ValueError, match="Page ID too long"):
        add_feedback_entry("valid question", "useful", ["a" * 300], path=feedback_file)


def test_feedback_valid_input_passes(tmp_path):
    from kb.feedback.store import add_feedback_entry

    feedback_file = tmp_path / "feedback.json"
    entry = add_feedback_entry(
        "x" * 100,
        "useful",
        ["concepts/rag", "entities/openai", "summaries/test"],
        notes="y" * 50,
        path=feedback_file,
    )
    assert entry["question"] == "x" * 100
    assert entry["rating"] == "useful"
    assert len(entry["cited_pages"]) == 3


# --- Verdict severity validation tests ---


def test_verdict_invalid_severity(tmp_path):
    from kb.lint.verdicts import add_verdict

    verdict_file = tmp_path / "verdicts.json"
    with pytest.raises(ValueError, match="Invalid issue severity"):
        add_verdict(
            "concepts/rag",
            "fidelity",
            "fail",
            issues=[{"severity": "critical", "description": "test"}],
            path=verdict_file,
        )


def test_verdict_valid_severity(tmp_path):
    from kb.lint.verdicts import add_verdict

    verdict_file = tmp_path / "verdicts.json"
    entry = add_verdict(
        "concepts/rag",
        "fidelity",
        "fail",
        issues=[{"severity": "error", "description": "test"}],
        path=verdict_file,
    )
    assert entry["verdict"] == "fail"
    assert len(entry["issues"]) == 1


def test_verdict_issue_not_dict(tmp_path):
    from kb.lint.verdicts import add_verdict

    verdict_file = tmp_path / "verdicts.json"
    with pytest.raises(ValueError, match="Each issue must be a dict"):
        add_verdict(
            "concepts/rag",
            "fidelity",
            "fail",
            issues=["not a dict"],
            path=verdict_file,
        )


# --- Refiner frontmatter validation tests ---


def test_refine_page_content_starts_with_frontmatter(tmp_path):
    from kb.review.refiner import refine_page

    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    page_dir = wiki_dir / "concepts"
    page_dir.mkdir()
    page = page_dir / "test.md"
    page.write_text(
        '---\ntitle: "Test"\nsource:\n  - "raw/articles/a.md"\n'
        "created: 2026-01-01\nupdated: 2026-01-01\n"
        "type: concept\nconfidence: stated\n---\n\nOld content\n"
    )
    result = refine_page(
        "concepts/test",
        "---\nThis breaks things",
        wiki_dir=wiki_dir,
        history_path=tmp_path / "history.json",
    )
    assert "error" in result
    assert "---" in result["error"]


def test_refine_page_valid_content(tmp_path):
    from kb.review.refiner import refine_page

    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    page_dir = wiki_dir / "concepts"
    page_dir.mkdir()
    page = page_dir / "test.md"
    page.write_text(
        '---\ntitle: "Test"\nsource:\n  - "raw/articles/a.md"\n'
        "created: 2026-01-01\nupdated: 2026-01-01\n"
        "type: concept\nconfidence: stated\n---\n\nOld content\n"
    )
    result = refine_page(
        "concepts/test",
        "New valid content here.\n\nMore content.",
        wiki_dir=wiki_dir,
        history_path=tmp_path / "history.json",
    )
    assert result["updated"] is True
    assert result["page_id"] == "concepts/test"
    # Verify the file was actually written with new content
    text = page.read_text(encoding="utf-8")
    assert "New valid content here." in text
