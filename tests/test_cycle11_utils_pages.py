from pathlib import Path


def test_import_page_id_and_scan_wiki_pages_succeeds():  # noqa: D103  # placeholder-for-task9
    from kb.utils.pages import page_id, scan_wiki_pages

    assert callable(page_id)
    assert callable(scan_wiki_pages)


def test_page_id_returns_lowercase_posix_relative_id():  # noqa: D103  # placeholder-for-task9
    from kb.utils.pages import page_id

    assert page_id(Path("wiki/concepts/foo.md"), wiki_dir=Path("wiki")) == "concepts/foo"


def test_page_id_lowercases_mixed_case_filename():  # noqa: D103  # placeholder-for-task9
    from kb.utils.pages import page_id

    assert page_id(Path("wiki/concepts/FOO.md"), wiki_dir=Path("wiki")) == "concepts/foo"


def test_scan_wiki_pages_returns_sorted_pages_and_skips_root_sentinels(
    tmp_path,
):  # noqa: D103  # placeholder-for-task9
    from kb.utils.pages import scan_wiki_pages

    wiki_dir = tmp_path / "wiki"
    sentinel_names = [
        "index.md",
        "_sources.md",
        "log.md",
        "contradictions.md",
        "purpose.md",
        "_categories.md",
        "_augment_proposals.md",
    ]
    for name in sentinel_names:
        (wiki_dir / name).parent.mkdir(parents=True, exist_ok=True)
        (wiki_dir / name).write_text(f"# {name}\n", encoding="utf-8")

    expected_pages = [
        wiki_dir / "concepts" / "a.md",
        wiki_dir / "concepts" / "b.md",
        wiki_dir / "entities" / "z.md",
    ]
    for page_path in reversed(expected_pages):
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text("# Page\n", encoding="utf-8")

    assert scan_wiki_pages(wiki_dir) == expected_pages


def test_private_page_id_alias_is_public_page_id():  # noqa: D103  # placeholder-for-task9
    from kb.utils.pages import _page_id, page_id

    assert _page_id is page_id
