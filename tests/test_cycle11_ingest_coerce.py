import pytest

from kb.ingest.pipeline import _coerce_str_field, _extract_entity_context, ingest_source
from kb.mcp import core as mcp_core


def _valid_extraction(**overrides):
    extraction = {
        "title": "ok",
        "core_argument": "ok",
        "key_claims": [],
        "entities_mentioned": [],
        "concepts_mentioned": [],
    }
    extraction.update(overrides)
    return extraction


def test_coerce_str_field_returns_empty_string_for_none():
    assert _coerce_str_field({"x": None}, "x") == ""


def test_coerce_str_field_rejects_int():
    with pytest.raises(ValueError):
        _coerce_str_field({"x": 42}, "x")


def test_coerce_str_field_rejects_float():
    with pytest.raises(ValueError):
        _coerce_str_field({"x": 3.14}, "x")


def test_coerce_str_field_rejects_dict():
    with pytest.raises(ValueError):
        _coerce_str_field({"x": {"a": 1}}, "x")


def test_coerce_str_field_rejects_list():
    with pytest.raises(ValueError):
        _coerce_str_field({"x": ["a", "b"]}, "x")


def test_coerce_str_field_returns_empty_string_for_missing_field():
    assert _coerce_str_field({}, "missing") == ""


def test_coerce_str_field_returns_string_value():
    assert _coerce_str_field({"x": "hello"}, "x") == "hello"


def test_ingest_source_rejects_non_string_summary_callee(tmp_project, monkeypatch):
    data_dir = tmp_project / ".data"
    data_dir.mkdir()
    monkeypatch.setattr("kb.compile.compiler.HASH_MANIFEST", data_dir / "hashes.json")
    source_path = tmp_project / "raw" / "articles" / "bad.md"
    source_path.write_text("# Bad\n\ncontent", encoding="utf-8")

    with pytest.raises(ValueError):
        ingest_source(
            source_path,
            source_type="article",
            extraction=_valid_extraction(core_argument=42),
            wiki_dir=tmp_project / "wiki",
            raw_dir=tmp_project / "raw",
            _skip_vector_rebuild=True,
        )


def test_extract_entity_context_rejects_non_string_context_field_cleanly():
    with pytest.raises(ValueError):
        _extract_entity_context(
            "ok",
            _valid_extraction(description=123, quotes="ok"),
        )


@pytest.mark.parametrize("source_type", ["comparison", "synthesis"])
def test_ingest_source_rejects_comparison_and_synthesis_with_kb_create_page_message(
    tmp_project, monkeypatch, source_type
):
    data_dir = tmp_project / ".data"
    data_dir.mkdir()
    manifest_path = data_dir / "hashes.json"
    monkeypatch.setattr("kb.compile.compiler.HASH_MANIFEST", manifest_path)
    source_path = tmp_project / "raw" / "articles" / f"{source_type}.md"
    source_path.write_text("# Unsupported\n\ncontent", encoding="utf-8")

    with pytest.raises(ValueError, match="kb_create_page"):
        ingest_source(
            source_path,
            source_type=source_type,
            extraction=_valid_extraction(),
            wiki_dir=tmp_project / "wiki",
            raw_dir=tmp_project / "raw",
            _skip_vector_rebuild=True,
        )

    assert not manifest_path.exists()
    assert list((tmp_project / "wiki" / "summaries").iterdir()) == []


@pytest.mark.parametrize("source_type", ["comparison", "synthesis"])
def test_kb_ingest_content_rejects_page_types_without_raw_file(
    tmp_project, monkeypatch, source_type
):
    raw_dir = tmp_project / "raw"
    before = sorted(path.relative_to(raw_dir) for path in raw_dir.rglob("*") if path.is_file())
    monkeypatch.setattr(mcp_core, "PROJECT_ROOT", tmp_project)
    monkeypatch.setattr(mcp_core, "RAW_DIR", raw_dir)
    monkeypatch.setattr(mcp_core, "SOURCE_TYPE_DIRS", {"article": raw_dir / "articles"})

    result = mcp_core.kb_ingest_content(
        content="# Unsupported\n\ncontent",
        filename=f"{source_type}.md",
        source_type=source_type,
        extraction_json='{"title": "Unsupported"}',
    )

    assert "kb_create_page" in result
    after = sorted(path.relative_to(raw_dir) for path in raw_dir.rglob("*") if path.is_file())
    assert after == before
