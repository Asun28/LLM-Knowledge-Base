from kb.mcp import core


def _assert_create_page_error(result: str) -> None:
    assert isinstance(result, str)
    assert "kb_create_page" in result
    assert "fake.md" not in result
    assert "x.md" not in result
    assert " x" not in result


def test_kb_ingest_comparison_names_kb_create_page(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(core, "RAW_DIR", tmp_path)
    source = tmp_path / "fake.md"
    source.write_text("raw content", encoding="utf-8")

    result = core.kb_ingest(source_path="fake.md", source_type="comparison")

    _assert_create_page_error(result)


def test_kb_ingest_synthesis_names_kb_create_page(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(core, "RAW_DIR", tmp_path)
    source = tmp_path / "fake.md"
    source.write_text("raw content", encoding="utf-8")

    result = core.kb_ingest(source_path="fake.md", source_type="synthesis")

    _assert_create_page_error(result)


def test_kb_ingest_content_comparison_names_kb_create_page(monkeypatch):
    monkeypatch.setattr(core, "SOURCE_TYPE_DIRS", {"article": object()})

    result = core.kb_ingest_content(
        content="x",
        filename="x.md",
        source_type="comparison",
        extraction_json="{}",
    )

    _assert_create_page_error(result)


def test_kb_ingest_content_synthesis_names_kb_create_page(monkeypatch):
    monkeypatch.setattr(core, "SOURCE_TYPE_DIRS", {"article": object()})

    result = core.kb_ingest_content(
        content="x",
        filename="x.md",
        source_type="synthesis",
        extraction_json="{}",
    )

    _assert_create_page_error(result)
