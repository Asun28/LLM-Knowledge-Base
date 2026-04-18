import json

from kb.config import MAX_INGEST_CONTENT_CHARS, QUERY_CONTEXT_MAX_CHARS
from kb.mcp import app as mcp_app
from kb.mcp import core


def test_kb_compile_scan_honors_wiki_dir(tmp_project, monkeypatch):
    monkeypatch.setattr("kb.config.PROJECT_ROOT", tmp_project)
    monkeypatch.setattr(mcp_app, "PROJECT_ROOT", tmp_project)
    source = tmp_project / "raw" / "articles" / "new.md"
    source.write_text("new article", encoding="utf-8")
    seen = {}

    def fake_find_changed_sources(*, raw_dir=None, manifest_path=None):
        seen["raw_dir"] = raw_dir
        seen["manifest_path"] = manifest_path
        return [source], []

    monkeypatch.setattr("kb.compile.compiler.find_changed_sources", fake_find_changed_sources)

    report = core.kb_compile_scan(wiki_dir=str(tmp_project / "wiki"))

    assert seen["raw_dir"] == tmp_project / "raw"
    assert seen["manifest_path"] == tmp_project / ".data" / "hashes.json"
    assert "new.md" in report


def test_kb_compile_scan_default_wiki_dir_preserves_prod(monkeypatch):
    seen = {}

    def fake_find_changed_sources(*, raw_dir=None, manifest_path=None):
        seen["raw_dir"] = raw_dir
        seen["manifest_path"] = manifest_path
        return [], []

    monkeypatch.setattr("kb.compile.compiler.find_changed_sources", fake_find_changed_sources)

    report = core.kb_compile_scan()

    assert seen == {"raw_dir": None, "manifest_path": None}
    assert report == "No new or changed sources found. Wiki is up to date."


def test_kb_ingest_rejects_oversized_content(tmp_project, monkeypatch):
    monkeypatch.setattr(core, "PROJECT_ROOT", tmp_project)
    monkeypatch.setattr(core, "RAW_DIR", tmp_project / "raw")
    source = tmp_project / "raw" / "articles" / "huge.md"
    content = "x" * (QUERY_CONTEXT_MAX_CHARS + 100)
    source.write_text(content, encoding="utf-8")

    result = core.kb_ingest(str(source), source_type="article")

    assert result.startswith("Error: source too long")
    assert str(len(content)) in result
    assert str(QUERY_CONTEXT_MAX_CHARS) in result
    assert not any((tmp_project / "wiki" / "summaries").iterdir())


def test_kb_ingest_content_rejects_oversized(tmp_project, monkeypatch):
    monkeypatch.setattr(
        core,
        "SOURCE_TYPE_DIRS",
        {"article": tmp_project / "raw" / "articles"},
    )
    content = "x" * (MAX_INGEST_CONTENT_CHARS + 1)
    extraction = {
        "title": "Oversized",
        "entities_mentioned": [],
        "concepts_mentioned": [],
    }

    result = core.kb_ingest_content(
        content=content,
        filename="oversized",
        source_type="article",
        extraction_json=json.dumps(extraction),
    )

    assert result.startswith("Error:")
    assert str(len(content)) in result
    assert not list((tmp_project / "raw" / "articles").iterdir())


def test_kb_ingest_accepts_at_limit(tmp_project, monkeypatch):
    monkeypatch.setattr(core, "PROJECT_ROOT", tmp_project)
    monkeypatch.setattr(core, "RAW_DIR", tmp_project / "raw")
    source = tmp_project / "raw" / "articles" / "limit.md"
    content = "x" * QUERY_CONTEXT_MAX_CHARS
    source.write_text(content, encoding="utf-8")

    def fake_load_template(source_type):
        assert source_type == "article"
        return {"name": "Article", "description": "Article template"}

    def fake_build_extraction_prompt(prompt_content, template):
        assert prompt_content == content
        assert template["name"] == "Article"
        return "PROMPT AT LIMIT"

    monkeypatch.setattr("kb.ingest.extractors.load_template", fake_load_template)
    monkeypatch.setattr(
        "kb.ingest.extractors.build_extraction_prompt", fake_build_extraction_prompt
    )

    result = core.kb_ingest(str(source), source_type="article")

    assert not result.startswith("Error: source too long")
    assert "PROMPT AT LIMIT" in result
    assert "limit.md" in result
