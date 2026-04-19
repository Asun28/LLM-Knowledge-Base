from pathlib import Path


def test_import_page_id_and_scan_wiki_pages_succeeds():  # noqa: D103  # placeholder-for-task9
    from kb.utils.pages import page_id, scan_wiki_pages

    assert callable(page_id)
    assert callable(scan_wiki_pages)


def test_graph_builder_re_exports_page_helpers_by_identity():  # noqa: D103
    from kb.graph.builder import page_id as builder_page_id
    from kb.graph.builder import scan_wiki_pages as builder_scan_wiki_pages
    from kb.utils.pages import page_id, scan_wiki_pages

    assert builder_page_id is page_id
    assert builder_scan_wiki_pages is scan_wiki_pages


def test_page_id_returns_lowercase_posix_relative_id():  # noqa: D103  # placeholder-for-task9
    from kb.utils.pages import page_id

    assert page_id(Path("wiki/concepts/foo.md"), wiki_dir=Path("wiki")) == "concepts/foo"


def test_page_id_lowercases_mixed_case_filename():  # noqa: D103  # placeholder-for-task9
    from kb.utils.pages import page_id

    assert page_id(Path("wiki/concepts/FOO.md"), wiki_dir=Path("wiki")) == "concepts/foo"


def test_page_id_normalizes_backslashes_to_posix_id():  # noqa: D103
    from kb.utils.pages import page_id

    assert page_id(Path("wiki\\concepts\\foo.md"), wiki_dir=Path("wiki")) == "concepts/foo"


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
        "hot.md",
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

    pages = scan_wiki_pages(wiki_dir)

    assert pages == expected_pages
    assert not {page.name for page in pages} & set(sentinel_names)
    assert pages == sorted(pages)


def test_private_page_id_alias_is_public_page_id():  # noqa: D103  # placeholder-for-task9
    from kb.utils.pages import _page_id, page_id

    assert _page_id is page_id


def test_cycle11_ac4_six_callers_resolve_page_helpers_via_canonical_module():
    """Behavioural R1 fix — drop the source-line scan that skipped indented
    imports like ``compile/compiler.py``'s function-local ``from kb.graph.builder
    import page_id as get_page_id`` inside ``detect_source_drift``.

    Import each caller module, then walk its module attributes. For the two
    symbols of interest (``page_id`` / ``scan_wiki_pages``), confirm each
    attribute either does not exist on the caller's module namespace OR resolves
    to the canonical identity ``kb.utils.pages.page_id`` / ``scan_wiki_pages``.
    This also proves that any `from kb.graph.builder import page_id` executed
    transparently via the cycle-11 re-export shim still reaches the canonical
    object, which is the actual contract the design doc names.
    """
    import importlib

    from kb.utils import pages as canonical

    caller_modules = [
        "kb.compile.linker",
        "kb.evolve.analyzer",
        "kb.lint.checks",
        "kb.lint.runner",
        "kb.lint.semantic",
        "kb.compile.compiler",
    ]
    for module_name in caller_modules:
        module = importlib.import_module(module_name)
        if hasattr(module, "page_id"):
            assert module.page_id is canonical.page_id, (
                f"{module_name}.page_id drifted from kb.utils.pages.page_id"
            )
        if hasattr(module, "scan_wiki_pages"):
            assert module.scan_wiki_pages is canonical.scan_wiki_pages, (
                f"{module_name}.scan_wiki_pages drifted from kb.utils.pages.scan_wiki_pages"
            )

    # R2 follow-up — the module-level identity check above misses
    # ``compile.compiler.detect_source_drift``'s FUNCTION-LOCAL imports
    # (``from kb.utils.pages import page_id as get_page_id`` inside the
    # function body). Exercise the function-local path behaviourally by
    # calling ``detect_source_drift`` with an empty raw dir + empty manifest:
    # the function runs through the ``from kb.utils.pages import ...`` line,
    # binds ``get_page_id``/``scan_wiki_pages`` to the canonical objects, and
    # returns a clean zero-changes dict. If the function-local import was
    # accidentally pointed at a different module OR if the helpers were
    # deleted outright, this call would raise ``ImportError``.


def test_cycle11_ac4_detect_source_drift_function_local_imports_resolve(tmp_path):
    """R2 follow-up — exercise compile.compiler.detect_source_drift's
    function-local imports to confirm the caller-migration contract holds
    at RUNTIME, not just at module-import time.
    """
    from kb.compile.compiler import detect_source_drift

    raw_dir = tmp_path / "raw"
    wiki_dir = tmp_path / "wiki"
    for sub in ("articles", "papers"):
        (raw_dir / sub).mkdir(parents=True, exist_ok=True)
    for sub in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        (wiki_dir / sub).mkdir(parents=True, exist_ok=True)
    manifest_path = tmp_path / ".data" / "hashes.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("{}", encoding="utf-8")

    report = detect_source_drift(
        raw_dir=raw_dir,
        wiki_dir=wiki_dir,
        manifest_path=manifest_path,
    )
    # Clean empty-corpus path succeeds only if the function-local
    # ``from kb.utils.pages import page_id, scan_wiki_pages`` resolves
    # correctly. An ImportError inside ``detect_source_drift`` would raise
    # here, catching any future regression that points the function-local
    # import at a stale module.
    assert isinstance(report, dict)
    assert "changed_sources" in report or "summary" in report
