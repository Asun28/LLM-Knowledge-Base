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
    """Path outside raw dir falls back to 'raw/<filename>'."""
    raw_dir = tmp_path / "project" / "raw"
    raw_dir.mkdir(parents=True)

    # Create source in a completely separate directory tree
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    source = other_dir / "stray-file.md"
    source.write_text("content", encoding="utf-8")

    result = make_source_ref(source, raw_dir=raw_dir)

    assert result == "raw/stray-file.md"


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
    """Passing raw_dir explicitly overrides the config default."""
    custom_raw = tmp_path / "custom_raw"
    (custom_raw / "videos").mkdir(parents=True)
    source = custom_raw / "videos" / "talk.md"
    source.write_text("content", encoding="utf-8")

    result = make_source_ref(source, raw_dir=custom_raw)

    assert result == "custom_raw/videos/talk.md"


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
