"""Tests for kb.utils.paths — canonical source reference computation."""

from unittest.mock import patch

from kb.utils.paths import make_source_ref

# ── Basic usage ──────────────────────────────────────────────────


def test_make_source_ref_normal(tmp_path):
    """File inside raw/articles/ produces 'raw/articles/<name>.md'."""
    raw_dir = tmp_path / "raw"
    (raw_dir / "articles").mkdir(parents=True)
    source = raw_dir / "articles" / "test.md"
    source.write_text("content", encoding="utf-8")

    result = make_source_ref(source, raw_dir=raw_dir)

    assert result == "raw/articles/test.md"


def test_make_source_ref_nested(tmp_path):
    """Deeply nested path inside raw/ produces correct forward-slash ref."""
    raw_dir = tmp_path / "raw"
    nested = raw_dir / "papers" / "2026" / "april" / "deep-paper.md"
    nested.parent.mkdir(parents=True)
    nested.write_text("content", encoding="utf-8")

    result = make_source_ref(nested, raw_dir=raw_dir)

    assert result == "raw/papers/2026/april/deep-paper.md"


# ── Fallback behavior ───────────────────────────────────────────


def test_make_source_ref_outside_raw_dir(tmp_path):
    """Path outside raw dir raises ValueError."""
    import pytest

    raw_dir = tmp_path / "project" / "raw"
    raw_dir.mkdir(parents=True)

    # Create source in a completely separate directory tree
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    source = other_dir / "stray-file.md"
    source.write_text("content", encoding="utf-8")

    with pytest.raises(ValueError, match="outside"):
        make_source_ref(source, raw_dir=raw_dir)


# ── Forward slashes (Windows safety) ────────────────────────────


def test_make_source_ref_forward_slashes(tmp_path):
    """Result always uses forward slashes, even on Windows."""
    raw_dir = tmp_path / "raw"
    (raw_dir / "repos").mkdir(parents=True)
    source = raw_dir / "repos" / "my-repo.md"
    source.write_text("content", encoding="utf-8")

    result = make_source_ref(source, raw_dir=raw_dir)

    assert "\\" not in result
    assert result == "raw/repos/my-repo.md"


# ── Explicit vs. default raw_dir ────────────────────────────────


def test_make_source_ref_with_explicit_raw_dir(tmp_path):
    """Passing raw_dir explicitly always produces a 'raw/...' prefix."""
    custom_raw = tmp_path / "custom_raw"
    (custom_raw / "videos").mkdir(parents=True)
    source = custom_raw / "videos" / "talk.md"
    source.write_text("content", encoding="utf-8")

    result = make_source_ref(source, raw_dir=custom_raw)

    assert result == "raw/videos/talk.md"


def test_make_source_ref_default_raw_dir(tmp_path):
    """When raw_dir is None, make_source_ref uses config.RAW_DIR."""
    # Mock RAW_DIR to point at a temporary raw directory
    mock_raw = tmp_path / "raw"
    (mock_raw / "articles").mkdir(parents=True)
    source = mock_raw / "articles" / "default-test.md"
    source.write_text("content", encoding="utf-8")

    with patch("kb.utils.paths.RAW_DIR", mock_raw):
        result = make_source_ref(source)

    assert result == "raw/articles/default-test.md"


# ── tmp_project fixture-contract pins (cycle 43 AC4 fold from test_cycle11_conftest_fixture.py) ───────


class TestTmpProjectFixtureContract:
    """Pin the conftest-defined ``tmp_project`` fixture's canonical wiki files.

    The fixture must create wiki/index.md, wiki/_sources.md, and wiki/log.md
    with specific frontmatter+body shapes. A future change that accidentally
    mutates these defaults would silently break every consuming test; this
    single-purpose pin catches the drift early.
    """

    EXPECTED_INDEX = (
        "---\n"
        "title: Wiki Index\n"
        "source: []\n"
        "type: index\n"
        "---\n\n"
        "# Knowledge Base Index\n\n"
        "## Pages\n\n"
        "*No pages yet.*\n\n"
        "## Entities\n\n"
        "*No pages yet.*\n\n"
        "## Concepts\n\n"
        "*No pages yet.*\n\n"
        "## Comparisons\n\n"
        "*No pages yet.*\n\n"
        "## Summaries\n\n"
        "*No pages yet.*\n\n"
        "## Synthesis\n\n"
        "*No pages yet.*\n"
    )

    EXPECTED_SOURCES = (
        "---\ntitle: Source Mapping\nsource: []\ntype: index\n---\n\n# Source Mapping\n"
    )

    def test_tmp_project_creates_canonical_index_sources_and_log(self, tmp_project):
        wiki = tmp_project / "wiki"

        assert (wiki / "index.md").read_text(encoding="utf-8") == self.EXPECTED_INDEX
        assert (wiki / "_sources.md").read_text(encoding="utf-8") == self.EXPECTED_SOURCES
        assert (wiki / "log.md").read_text(encoding="utf-8") == "# Wiki Log\n\n"
