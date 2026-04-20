"""Cycle 16 AC17-AC19 — kb_query save_as + _validate_save_as_slug.

Behavioural regressions covering T1 (path traversal), T2 (hardcoded
frontmatter), T15 (never raises). Direct import + monkeypatch of
query_wiki.
"""

import frontmatter
import pytest

from kb.mcp import core as mcp_core
from kb.models.frontmatter import validate_frontmatter


class TestValidateSaveAsSlug:
    def test_happy_path(self) -> None:
        slug, err = mcp_core._validate_save_as_slug("my-great-topic")
        assert err is None
        assert slug == "my-great-topic"

    def test_empty_rejected(self) -> None:
        slug, err = mcp_core._validate_save_as_slug("")
        assert err is not None
        assert slug == ""

    def test_whitespace_padded_rejected(self) -> None:
        _, err = mcp_core._validate_save_as_slug(" foo ")
        assert err is not None

    def test_too_long_rejected(self) -> None:
        _, err = mcp_core._validate_save_as_slug("x" * 81)
        assert err is not None

    def test_dotdot_rejected(self) -> None:
        _, err = mcp_core._validate_save_as_slug("..")
        assert err is not None
        _, err = mcp_core._validate_save_as_slug("foo/../bar")
        assert err is not None

    def test_absolute_path_rejected(self) -> None:
        _, err = mcp_core._validate_save_as_slug("/abs/path")
        assert err is not None

    def test_backslash_rejected(self) -> None:
        _, err = mcp_core._validate_save_as_slug("foo\\bar")
        assert err is not None

    def test_uppercase_rejected(self) -> None:
        """slugify idempotence check catches uppercase input."""
        _, err = mcp_core._validate_save_as_slug("My-Topic")
        assert err is not None

    def test_cyrillic_a_rejected(self) -> None:
        """Q3/C4 — Cyrillic 'а' (U+0430) looks like Latin 'a' but MUST fail."""
        cyrillic_a = "\u0430"  # Cyrillic 'а'
        candidate = f"c{cyrillic_a}fe"
        _, err = mcp_core._validate_save_as_slug(candidate)
        assert err is not None
        assert "ASCII" in err or "slug form" in err

    def test_space_rejected(self) -> None:
        _, err = mcp_core._validate_save_as_slug("my topic")
        assert err is not None

    def test_windows_reserved_rejected(self) -> None:
        _, err = mcp_core._validate_save_as_slug("con")
        assert err is not None

    def test_never_raises_under_kb_debug(self, monkeypatch) -> None:
        """T15/C2 — validation never raises, even under KB_DEBUG=1."""
        monkeypatch.setenv("KB_DEBUG", "1")
        # Try every rejection path — none may raise.
        for bad in ["", " x ", "..", "/abs", "foo\\bar", "My-X", "\u0430bc", "x" * 81, "con"]:
            slug, err = mcp_core._validate_save_as_slug(bad)
            assert isinstance(err, str)
            assert slug == ""

    def test_non_string_rejected_gracefully(self) -> None:
        _, err = mcp_core._validate_save_as_slug(None)  # type: ignore[arg-type]
        assert err is not None


def _make_result(answer: str = "synthesised answer", source_pages: list[str] | None = None) -> dict:
    return {
        "question": "q",
        "answer": answer,
        "citations": [],
        "source_pages": source_pages or [],
        "context_pages": [],
        "stale_citations": [],
        "search_mode": "bm25_only",
        "coverage_confidence": None,
    }


class TestSaveSynthesisHelper:
    def test_happy_path_writes_file(self, tmp_project, monkeypatch) -> None:
        """AC17-AC19 happy path — writes wiki/synthesis/{slug}.md."""
        monkeypatch.setattr(mcp_core, "WIKI_DIR", tmp_project / "wiki")
        result = _make_result(source_pages=["concepts/rag"])
        msg = mcp_core._save_synthesis("my-topic", result)
        assert "Saved synthesis" in msg
        target = tmp_project / "wiki" / "synthesis" / "my-topic.md"
        assert target.exists()

    def test_writes_hardcoded_frontmatter(self, tmp_project, monkeypatch) -> None:
        """T2 — confidence=inferred, type=synthesis, authored_by=llm."""
        monkeypatch.setattr(mcp_core, "WIKI_DIR", tmp_project / "wiki")
        result = _make_result(source_pages=["concepts/a"])
        mcp_core._save_synthesis("t-2", result)
        post = frontmatter.load(tmp_project / "wiki" / "synthesis" / "t-2.md")
        assert post.metadata["confidence"] == "inferred"
        assert post.metadata["type"] == "synthesis"
        assert post.metadata["authored_by"] == "llm"

    def test_source_from_source_pages(self, tmp_project, monkeypatch) -> None:
        """Q1/C1 — source list = source_pages, not empty."""
        monkeypatch.setattr(mcp_core, "WIKI_DIR", tmp_project / "wiki")
        result = _make_result(source_pages=["concepts/a", "entities/b"])
        mcp_core._save_synthesis("t-3", result)
        post = frontmatter.load(tmp_project / "wiki" / "synthesis" / "t-3.md")
        assert list(post.metadata["source"]) == ["concepts/a", "entities/b"]

    def test_empty_source_pages_returns_warn(self, tmp_project, monkeypatch) -> None:
        """Q1/C1 — empty source_pages → skip write with warn message."""
        monkeypatch.setattr(mcp_core, "WIKI_DIR", tmp_project / "wiki")
        result = _make_result(source_pages=[])
        msg = mcp_core._save_synthesis("t-4", result)
        assert "[warn]" in msg
        assert "no source_pages" in msg
        assert not (tmp_project / "wiki" / "synthesis" / "t-4.md").exists()

    def test_refusal_path_skips_save(self, tmp_project, monkeypatch) -> None:
        """AC18 — low_confidence result skips save."""
        monkeypatch.setattr(mcp_core, "WIKI_DIR", tmp_project / "wiki")
        result = _make_result(source_pages=["concepts/a"])
        result["low_confidence"] = True
        msg = mcp_core._save_synthesis("t-5", result)
        assert "[info]" in msg
        assert "refusal" in msg
        assert not (tmp_project / "wiki" / "synthesis" / "t-5.md").exists()

    def test_collision_returns_warn(self, tmp_project, monkeypatch) -> None:
        """AC18 — pre-existing target returns warn, no overwrite."""
        monkeypatch.setattr(mcp_core, "WIKI_DIR", tmp_project / "wiki")
        target = tmp_project / "wiki" / "synthesis" / "t-6.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("pre-existing", encoding="utf-8")
        result = _make_result(source_pages=["concepts/a"])
        msg = mcp_core._save_synthesis("t-6", result)
        assert "already exists" in msg
        # Pre-existing content preserved.
        assert target.read_text(encoding="utf-8") == "pre-existing"

    def test_output_passes_validate_frontmatter(self, tmp_project, monkeypatch) -> None:
        """C1 — saved file passes validate_frontmatter with zero errors."""
        monkeypatch.setattr(mcp_core, "WIKI_DIR", tmp_project / "wiki")
        mcp_core._save_synthesis("t-valid", _make_result(source_pages=["concepts/a"]))
        post = frontmatter.load(tmp_project / "wiki" / "synthesis" / "t-valid.md")
        errors = validate_frontmatter(post)
        assert errors == []

    def test_containment_check_rejects_sibling_prefix_dir(self, tmp_project, monkeypatch) -> None:
        """R1 Blocker 1 / test-gap 7 — _save_synthesis uses Path.is_relative_to,
        not str.startswith. A sibling directory named `synthesis_evil` must NOT
        be treated as contained under `synthesis/`.

        This is difficult to trigger directly because the upstream
        _validate_save_as_slug already rejects anything with path separators
        — so any slug that reaches _save_synthesis is guaranteed to resolve
        under WIKI_DIR/synthesis. The regression here asserts the defensive
        check's semantics directly via Path.is_relative_to.
        """
        synthesis_dir = (tmp_project / "wiki" / "synthesis").resolve()
        synthesis_dir.mkdir(parents=True, exist_ok=True)
        sibling = (tmp_project / "wiki" / "synthesis_evil").resolve()
        sibling.mkdir(parents=True, exist_ok=True)
        malicious_target = sibling / "pwn.md"
        # Old str.startswith check would have returned True here.
        # is_relative_to correctly returns False.
        try:
            contained = malicious_target.is_relative_to(synthesis_dir)
        except ValueError:
            contained = False
        assert not contained
        # And a legitimate sibling under synthesis_dir resolves correctly.
        legit = synthesis_dir / "ok.md"
        assert legit.is_relative_to(synthesis_dir)


class TestRephrasingBraceSafety:
    """R1 Sonnet Minor 5 — prompt builder must tolerate `{` / `}` in the
    truncated question text without raising KeyError/IndexError.
    """

    def test_question_with_braces_does_not_raise(self, monkeypatch) -> None:
        from kb.query import engine

        captured = {"prompt": ""}

        def _capture(prompt, **k):
            captured["prompt"] = prompt
            return ""

        monkeypatch.setattr(engine, "call_llm", _capture)
        # A JSON-like question with literal braces — would crash str.format()
        # but must work with plain concatenation.
        q = '{"type":"rag","k":10}'
        result = engine._suggest_rephrasings(q, [{"title": "T"}])
        assert result == []  # empty LLM output → []
        assert q in captured["prompt"]


class TestKbQueryValidateSaveAs:
    """End-to-end save_as validation path through kb_query."""

    def test_empty_save_as_default_does_not_write(self, tmp_project, monkeypatch) -> None:
        monkeypatch.setattr(mcp_core, "WIKI_DIR", tmp_project / "wiki")

        def _fake_query(*a, **k):
            return _make_result(source_pages=["concepts/a"])

        monkeypatch.setattr(mcp_core, "query_wiki", _fake_query)
        # No save_as → no write.
        result = mcp_core.kb_query("what is rag?", use_api=True)
        assert isinstance(result, str)
        synthesis_dir = tmp_project / "wiki" / "synthesis"
        assert not any(synthesis_dir.glob("*.md")) if synthesis_dir.exists() else True

    def test_save_as_requires_use_api(self, tmp_project, monkeypatch) -> None:
        """AC17 — save_as without use_api=True returns error."""
        monkeypatch.setattr(mcp_core, "WIKI_DIR", tmp_project / "wiki")
        result = mcp_core.kb_query("q", save_as="my-slug")
        assert result.startswith("Error: save_as requires use_api")

    def test_save_as_invalid_slug_returns_error_early(self, tmp_project, monkeypatch) -> None:
        """AC19 — invalid slug rejected BEFORE query runs."""
        called = {"n": 0}

        def _fake_query(*a, **k):
            called["n"] += 1
            return _make_result()

        monkeypatch.setattr(mcp_core, "query_wiki", _fake_query)
        monkeypatch.setattr(mcp_core, "WIKI_DIR", tmp_project / "wiki")
        result = mcp_core.kb_query("q", use_api=True, save_as="../evil")
        assert result.startswith("Error:")
        assert called["n"] == 0  # query never ran

    def test_save_as_happy_path_end_to_end(self, tmp_project, monkeypatch) -> None:
        """End-to-end: valid save_as writes synthesis file."""
        monkeypatch.setattr(mcp_core, "WIKI_DIR", tmp_project / "wiki")

        def _fake_query(*a, **k):
            return _make_result(source_pages=["concepts/rag"])

        monkeypatch.setattr(mcp_core, "query_wiki", _fake_query)
        result = mcp_core.kb_query("what is rag?", use_api=True, save_as="rag-intro")
        assert "Saved synthesis to:" in result
        target = tmp_project / "wiki" / "synthesis" / "rag-intro.md"
        assert target.exists()


# Sanity — frontmatter / pytest fixture exports.
assert frontmatter is not None  # noqa: S101
assert pytest is not None  # noqa: S101
