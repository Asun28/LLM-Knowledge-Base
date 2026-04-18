import json

import pytest

from kb.ingest.pipeline import _build_summary_content, _coerce_str_field, ingest_source
from kb.utils.hashing import hash_bytes


@pytest.mark.parametrize(
    ("extraction", "field", "expected", "type_name"),
    [
        ({"title": "A title"}, "title", "A title", None),
        ({"title": ""}, "title", "", None),
        ({}, "title", "", None),
        ({"title": None}, "title", "", None),
        ({"title": 1}, "title", None, "int"),
        ({"title": 1.5}, "title", None, "float"),
        ({"title": {"nested": "dict"}}, "title", None, "dict"),
        ({"title": ["list"]}, "title", None, "list"),
        ({"title": b"bytes"}, "title", None, "bytes"),
        ({"title": True}, "title", None, "bool"),
    ],
)
def test_coerce_str_field_accepts_string_missing_none_and_rejects_non_strings(
    extraction, field, expected, type_name
):
    before = dict(extraction)

    if type_name is None:
        assert _coerce_str_field(extraction, field) == expected
    else:
        with pytest.raises(ValueError, match=rf"title.*must be string.*{type_name}"):
            _coerce_str_field(extraction, field)
    assert extraction == before


def test_ingest_source_rejects_non_string_extraction_before_writes_and_manifest(
    tmp_project, monkeypatch
):
    data_dir = tmp_project / ".data"
    data_dir.mkdir()
    manifest_path = data_dir / "hashes.json"
    raw_path = tmp_project / "raw" / "articles" / "bad.md"
    raw_path.write_text("# Bad\n\nBenign content.", encoding="utf-8")
    raw_hash = hash_bytes(raw_path.read_bytes())
    monkeypatch.setattr("kb.compile.compiler.HASH_MANIFEST", manifest_path)

    with pytest.raises(ValueError, match=r"core_argument.*must be string.*dict"):
        ingest_source(
            raw_path,
            "article",
            extraction={"title": "Bad", "core_argument": {"nested": "dict"}},
            wiki_dir=tmp_project / "wiki",
            raw_dir=tmp_project / "raw",
            _skip_vector_rebuild=True,
        )

    assert list((tmp_project / "wiki" / "summaries").iterdir()) == []
    assert list((tmp_project / "wiki" / "entities").iterdir()) == []
    assert list((tmp_project / "wiki" / "concepts").iterdir()) == []
    if manifest_path.exists():
        assert raw_hash not in json.loads(manifest_path.read_text(encoding="utf-8")).values()


def test_build_summary_content_defensively_rejects_non_string_fields():
    with pytest.raises(ValueError, match=r"core_argument.*must be string.*dict"):
        _build_summary_content(
            {"title": "Bad", "core_argument": {"nested": "dict"}},
            "article",
        )


def test_ingest_source_accepts_valid_string_extraction(tmp_project, monkeypatch):
    data_dir = tmp_project / ".data"
    data_dir.mkdir()
    monkeypatch.setattr("kb.compile.compiler.HASH_MANIFEST", data_dir / "hashes.json")
    raw_path = tmp_project / "raw" / "articles" / "good.md"
    raw_path.write_text("# Good\n\nBenign content.", encoding="utf-8")

    result = ingest_source(
        raw_path,
        "article",
        extraction={
            "title": "Good Article",
            "author": "A. Writer",
            "core_argument": "A valid overview.",
            "entities_mentioned": [],
            "concepts_mentioned": [],
        },
        wiki_dir=tmp_project / "wiki",
        raw_dir=tmp_project / "raw",
        _skip_vector_rebuild=True,
    )

    assert result["pages_created"]
    assert list((tmp_project / "wiki" / "summaries").glob("*.md"))
