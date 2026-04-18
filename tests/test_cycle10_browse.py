"""Cycle 10 AC21 browse regression pins."""

import pytest


def test_kb_read_page_rejects_case_insensitive_ambiguity_regression_pin(
    tmp_path, tmp_wiki, monkeypatch
):
    probe_dir = tmp_path / "case_probe"
    probe_dir.mkdir()
    upper_probe = probe_dir / "Foo.md"
    lower_probe = probe_dir / "foo.md"
    upper_probe.write_text("upper", encoding="utf-8")
    lower_probe.write_text("lower", encoding="utf-8")
    if upper_probe.read_text(encoding="utf-8") == lower_probe.read_text(encoding="utf-8"):
        pytest.skip("case-insensitive FS detected via capability probe")

    from kb import config
    from kb.mcp import app as mcp_app
    from kb.mcp import browse

    concepts_dir = tmp_wiki / "concepts"
    (concepts_dir / "foo-bar.md").write_text("lower content", encoding="utf-8")
    (concepts_dir / "Foo-Bar.md").write_text("upper content", encoding="utf-8")
    monkeypatch.setattr(config, "WIKI_DIR", tmp_wiki)
    monkeypatch.setattr(mcp_app, "WIKI_DIR", tmp_wiki)
    monkeypatch.setattr(browse, "WIKI_DIR", tmp_wiki)

    result = browse.kb_read_page("concepts/FOO-BAR")

    assert result.startswith("Error: ambiguous page_id")
    assert "foo-bar" in result
    assert "Foo-Bar" in result
