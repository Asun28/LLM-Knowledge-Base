from kb.evolve.analyzer import analyze_coverage


def test_bare_slug_link_not_reported_as_orphan(tmp_project):
    wiki_dir = tmp_project / "wiki"
    page_a = wiki_dir / "concepts" / "a.md"
    page_b = wiki_dir / "concepts" / "b.md"

    page_a.write_text(
        "---\ntitle: A\ntype: concept\n---\n\nSee [[b]].\n",
        encoding="utf-8",
    )
    page_b.write_text(
        "---\ntitle: B\ntype: concept\n---\n\nTarget concept.\n",
        encoding="utf-8",
    )

    report = analyze_coverage(wiki_dir=wiki_dir)

    assert "concepts/b" not in report["orphan_concepts"]
