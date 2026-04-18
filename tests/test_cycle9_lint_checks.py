import frontmatter.default_handlers

from kb.lint.checks import check_source_coverage


def test_check_source_coverage_parses_yaml_once_per_page(tmp_project, monkeypatch):
    wiki_dir = tmp_project / "wiki"
    raw_dir = tmp_project / "raw"
    articles_dir = raw_dir / "articles"

    for name in ("a", "b", "c"):
        (articles_dir / f"{name}.md").write_text(f"{name} source\n", encoding="utf-8")
        (wiki_dir / "concepts" / f"{name}.md").write_text(
            (
                "---\n"
                f'title: "{name.upper()}"\n'
                "source:\n"
                f'  - "raw/articles/{name}.md"\n'
                "created: 2026-04-18\n"
                "updated: 2026-04-18\n"
                "type: concept\n"
                "confidence: stated\n"
                "---\n\n"
                f"{name.upper()} references raw/articles/{name}.md in body text.\n"
            ),
            encoding="utf-8",
        )

    original_load = frontmatter.default_handlers.yaml.load

    def spy_load(*args, **kwargs):
        spy_load.call_count += 1
        return original_load(*args, **kwargs)

    spy_load.call_count = 0
    monkeypatch.setattr(frontmatter.default_handlers.yaml, "load", spy_load)

    issues = check_source_coverage(wiki_dir=wiki_dir, raw_dir=raw_dir)

    assert spy_load.call_count == 3
    orphan_sources = {issue["source"] for issue in issues if issue["check"] == "source_coverage"}
    assert orphan_sources == set()
