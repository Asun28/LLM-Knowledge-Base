"""Cycle 14 TASK 7 — /llms.txt, /llms-full.txt, /graph.jsonld publish module.

Covers AC20, AC21, AC22. Threats: T1 (path containment), T2 (belief/confidence
filter), T3 (JSON injection via title), T8 (URL disclosure).
"""

from __future__ import annotations

import json
from pathlib import Path

import frontmatter
from click.testing import CliRunner

from kb.compile import publish as publish_mod
from kb.compile.publish import build_graph_jsonld, build_llms_full_txt, build_llms_txt


def _wiki_with_pages(tmp_path: Path, page_specs: list[dict]) -> Path:
    wiki = tmp_path / "wiki"
    for sd in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        (wiki / sd).mkdir(parents=True)
    for spec in page_specs:
        subdir = spec.get("subdir", "concepts")
        pid = spec["id"]
        post = frontmatter.Post(content=spec.get("body", "body"))
        post.metadata["title"] = spec["title"]
        post.metadata["source"] = spec.get("source", f"raw/articles/{pid}.md")
        post.metadata["created"] = "2026-04-20"
        post.metadata["updated"] = "2026-04-20"
        post.metadata["type"] = spec.get("type", "concept")
        post.metadata["confidence"] = spec.get("confidence", "stated")
        if "belief_state" in spec:
            post.metadata["belief_state"] = spec["belief_state"]
        path = wiki / subdir / f"{pid}.md"
        path.write_text(frontmatter.dumps(post, sort_keys=False), encoding="utf-8")
    return wiki


class TestLlmsTxtBasics:
    """AC22(a) — one line per page under type headers, ordered by page_id."""

    def test_one_line_per_page(self, tmp_path):
        wiki = _wiki_with_pages(
            tmp_path,
            [
                {"id": "alpha", "title": "Alpha Page", "type": "concept"},
                {"id": "beta", "title": "Beta Page", "type": "concept"},
                {"id": "gamma", "title": "Gamma Page", "type": "entity", "subdir": "entities"},
            ],
        )
        out = tmp_path / "llms.txt"
        build_llms_txt(wiki, out)
        text = out.read_text(encoding="utf-8")
        # Two type headers
        assert "## concept" in text
        assert "## entity" in text
        # Three title lines
        assert "Alpha Page" in text
        assert "Beta Page" in text
        assert "Gamma Page" in text

    def test_ordered_by_id(self, tmp_path):
        wiki = _wiki_with_pages(
            tmp_path,
            [
                {"id": "zebra", "title": "Z"},
                {"id": "apple", "title": "A"},
                {"id": "mango", "title": "M"},
            ],
        )
        out = tmp_path / "llms.txt"
        build_llms_txt(wiki, out)
        text = out.read_text(encoding="utf-8")
        # Find the three title lines in text
        a_idx = text.find("A — ")
        m_idx = text.find("M — ")
        z_idx = text.find("Z — ")
        assert 0 < a_idx < m_idx < z_idx


class TestFilterRetractedContradictedSpeculative:
    """AC22(a) + Threat T2 — epistemic filter."""

    def test_retracted_filtered(self, tmp_path):
        wiki = _wiki_with_pages(
            tmp_path,
            [
                {"id": "good", "title": "Good Page"},
                {"id": "bad", "title": "Bad Page", "belief_state": "retracted"},
            ],
        )
        out = tmp_path / "llms.txt"
        build_llms_txt(wiki, out)
        text = out.read_text(encoding="utf-8")
        assert "Good Page" in text
        assert "Bad Page" not in text
        assert "[!excluded]" in text

    def test_contradicted_filtered(self, tmp_path):
        wiki = _wiki_with_pages(
            tmp_path,
            [
                {"id": "good", "title": "Good Page"},
                {"id": "conflict", "title": "Conflict", "belief_state": "contradicted"},
            ],
        )
        out = tmp_path / "llms.txt"
        build_llms_txt(wiki, out)
        text = out.read_text(encoding="utf-8")
        assert "Conflict" not in text

    def test_speculative_confidence_filtered(self, tmp_path):
        wiki = _wiki_with_pages(
            tmp_path,
            [
                {"id": "solid", "title": "Solid", "confidence": "stated"},
                {"id": "stub", "title": "Stub", "confidence": "speculative"},
            ],
        )
        out = tmp_path / "llms.txt"
        build_llms_txt(wiki, out)
        text = out.read_text(encoding="utf-8")
        assert "Solid" in text
        assert "Stub" not in text

    def test_all_three_filters_in_full_output(self, tmp_path):
        wiki = _wiki_with_pages(
            tmp_path,
            [
                {"id": "good", "title": "Good"},
                {"id": "r", "title": "R", "belief_state": "retracted"},
                {"id": "c", "title": "C", "belief_state": "contradicted"},
                {"id": "s", "title": "S", "confidence": "speculative"},
            ],
        )
        out = tmp_path / "llms-full.txt"
        build_llms_full_txt(wiki, out)
        text = out.read_text(encoding="utf-8")
        assert "Good" in text
        assert "# R" not in text
        assert "# C" not in text
        assert "# S" not in text

    def test_jsonld_filter(self, tmp_path):
        wiki = _wiki_with_pages(
            tmp_path,
            [
                {"id": "good", "title": "Good"},
                {"id": "r", "title": "Retracted", "belief_state": "retracted"},
            ],
        )
        out = tmp_path / "graph.jsonld"
        build_graph_jsonld(wiki, out)
        data = json.loads(out.read_text(encoding="utf-8"))
        names = [n["name"] for n in data["@graph"]]
        assert "Good" in names
        assert "Retracted" not in names


class TestJsonLdStructure:
    """AC22(c)(d) — JSON-LD parses; url is relative POSIX (T8)."""

    def test_parses_as_valid_json_ld(self, tmp_path):
        wiki = _wiki_with_pages(tmp_path, [{"id": "a", "title": "A"}])
        out = tmp_path / "graph.jsonld"
        build_graph_jsonld(wiki, out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["@context"] == "https://schema.org/"
        assert "@graph" in data
        assert isinstance(data["@graph"], list)

    def test_url_is_relative_posix(self, tmp_path):
        wiki = _wiki_with_pages(tmp_path, [{"id": "a", "title": "A"}])
        out = tmp_path / "graph.jsonld"
        build_graph_jsonld(wiki, out)
        data = json.loads(out.read_text(encoding="utf-8"))
        node = data["@graph"][0]
        assert node["url"] == "concepts/a.md"
        # T8: no absolute path / drive letter / scheme
        text = out.read_text(encoding="utf-8")
        assert "file://" not in text
        assert str(tmp_path) not in text

    def test_creative_work_type(self, tmp_path):
        wiki = _wiki_with_pages(tmp_path, [{"id": "a", "title": "A"}])
        out = tmp_path / "graph.jsonld"
        build_graph_jsonld(wiki, out)
        data = json.loads(out.read_text(encoding="utf-8"))
        for node in data["@graph"]:
            assert node["@type"] == "CreativeWork"


class TestJsonInjectionDefence:
    """Threat T3 — titles with ", \\n, \\u2028 round-trip without breaking."""

    def test_title_with_quote_roundtrips(self, tmp_path):
        wiki = _wiki_with_pages(
            tmp_path,
            [
                {
                    "id": "quote",
                    "title": 'Title with "quote" and ] bracket and },{ closer',
                }
            ],
        )
        out = tmp_path / "graph.jsonld"
        build_graph_jsonld(wiki, out)
        data = json.loads(out.read_text(encoding="utf-8"))
        names = [n["name"] for n in data["@graph"]]
        assert any("quote" in n and "bracket" in n for n in names)

    def test_title_with_unicode_line_separator(self, tmp_path):
        wiki = _wiki_with_pages(tmp_path, [{"id": "unicode", "title": "multi\u2028line\ntitle"}])
        # Plain-text variant — llms.txt must collapse newlines
        out_txt = tmp_path / "llms.txt"
        build_llms_txt(wiki, out_txt)
        text = out_txt.read_text(encoding="utf-8")
        # Title line shouldn't contain bare \n or U+2028 that breaks one-
        # line-per-page contract.
        for line in text.splitlines():
            assert "\u2028" not in line

    def test_jsonld_roundtrip_with_unicode(self, tmp_path):
        wiki = _wiki_with_pages(tmp_path, [{"id": "u", "title": "title\u2028embedded"}])
        out = tmp_path / "graph.jsonld"
        build_graph_jsonld(wiki, out)
        # Must parse even with U+2028 in the title
        data = json.loads(out.read_text(encoding="utf-8"))
        assert len(data["@graph"]) == 1


class TestLlmsFullSizeCap:
    """AC22(e) — oversized first page emits [!oversized] marker."""

    def test_oversized_first_page_marker(self, tmp_path, monkeypatch):
        # Set a tiny cap to force oversize.
        monkeypatch.setattr(publish_mod, "LLMS_FULL_MAX_BYTES", 256)
        wiki = _wiki_with_pages(
            tmp_path,
            [
                {"id": "big", "title": "Big Page", "body": "x" * 10_000},
            ],
        )
        out = tmp_path / "llms-full.txt"
        build_llms_full_txt(wiki, out)
        text = out.read_text(encoding="utf-8")
        assert "[!oversized" in text

    def test_truncates_with_footer_mid_list(self, tmp_path, monkeypatch):
        monkeypatch.setattr(publish_mod, "LLMS_FULL_MAX_BYTES", 512)
        specs = [{"id": f"page-{i:03d}", "title": f"P{i}", "body": "y" * 200} for i in range(10)]
        wiki = _wiki_with_pages(tmp_path, specs)
        out = tmp_path / "llms-full.txt"
        build_llms_full_txt(wiki, out)
        text = out.read_text(encoding="utf-8")
        assert "[TRUNCATED" in text


class TestEmptyWikiValidOutputs:
    """AC22(f) — empty wiki produces valid (empty) outputs."""

    def test_empty_llms_txt(self, tmp_path):
        wiki = _wiki_with_pages(tmp_path, [])
        out = tmp_path / "llms.txt"
        build_llms_txt(wiki, out)
        text = out.read_text(encoding="utf-8")
        assert text.startswith("# LLMs index")

    def test_empty_jsonld(self, tmp_path):
        wiki = _wiki_with_pages(tmp_path, [])
        out = tmp_path / "graph.jsonld"
        build_graph_jsonld(wiki, out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["@context"] == "https://schema.org/"
        assert data["@graph"] == []


class TestKbPublishCli:
    """AC22 — kb publish CLI wires all three builders."""

    def test_all_format_writes_three_files(self, tmp_path, monkeypatch):
        from kb.cli import cli

        wiki = _wiki_with_pages(tmp_path, [{"id": "a", "title": "A"}])
        out_dir = tmp_path / "outputs"
        out_dir.mkdir()  # pre-existing operator dir (outside PROJECT_ROOT)
        import kb.config as kb_config_mod

        monkeypatch.setattr(kb_config_mod, "WIKI_DIR", wiki)

        runner = CliRunner()
        result = runner.invoke(cli, ["publish", "--out-dir", str(out_dir), "--format", "all"])
        assert result.exit_code == 0, result.output
        assert (out_dir / "llms.txt").exists()
        assert (out_dir / "llms-full.txt").exists()
        assert (out_dir / "graph.jsonld").exists()

    def test_format_llms_only_one_file(self, tmp_path, monkeypatch):
        from kb.cli import cli

        wiki = _wiki_with_pages(tmp_path, [{"id": "a", "title": "A"}])
        out_dir = tmp_path / "outputs"
        out_dir.mkdir()
        import kb.config as kb_config_mod

        monkeypatch.setattr(kb_config_mod, "WIKI_DIR", wiki)

        runner = CliRunner()
        result = runner.invoke(cli, ["publish", "--out-dir", str(out_dir), "--format", "llms"])
        assert result.exit_code == 0, result.output
        assert (out_dir / "llms.txt").exists()
        assert not (out_dir / "llms-full.txt").exists()
        assert not (out_dir / "graph.jsonld").exists()


class TestOutDirContainment:
    """Threat T1 — --out-dir outside PROJECT_ROOT requires pre-existing dir."""

    def test_nonexistent_outside_project_rejected(self, tmp_path):
        from kb.cli import cli

        runner = CliRunner()
        # A path far outside PROJECT_ROOT that does NOT exist.
        far_away = tmp_path / "nonexistent-subdir" / "deeper"
        result = runner.invoke(cli, ["publish", "--out-dir", str(far_away), "--format", "llms"])
        assert result.exit_code != 0
        assert "does not pre-exist" in result.output or "Usage" in result.output

    def test_existing_outside_project_allowed(self, tmp_path, monkeypatch):
        from kb.cli import cli

        wiki = _wiki_with_pages(tmp_path, [{"id": "a", "title": "A"}])
        outside = tmp_path / "operator-dir"
        outside.mkdir()
        import kb.config as kb_config_mod

        monkeypatch.setattr(kb_config_mod, "WIKI_DIR", wiki)

        runner = CliRunner()
        result = runner.invoke(cli, ["publish", "--out-dir", str(outside), "--format", "llms"])
        assert result.exit_code == 0, result.output
        assert (outside / "llms.txt").exists()
