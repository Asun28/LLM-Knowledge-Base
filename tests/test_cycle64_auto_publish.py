"""Cycle 64 — Cluster D — `compile/publish.py::auto_publish_after_compile`
+ `compile/compiler.py::compile_wiki` AC14 hook (AC13–AC15.5).

Regression tests proving:
- AC13: auto_publish_after_compile emits llms.txt + llms-full.txt + graph.jsonld
  + sitemap.xml under `<wiki_dir>.parent/_publish/`.
- AC13: per-builder errors caught + logged WARNING; remaining builders continue.
- AC14: compile_wiki post-success invokes auto_publish_after_compile by default.
- AC14: KB_DISABLE_COMPILE_AUTO_PUBLISH=1 (call-time env) disables the hook.
- AC15: publish failure does NOT fail compile_wiki.
- AC15.5: auto_publish_after_compile rejects out_dir outside PROJECT_ROOT
  (M4 / T10 mitigation; raises ValidationError per
  `_validate_path_under_project_root`).

Per cycle-40 L3: each test diverges expected vs reverted behaviour.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kb.compile.publish import auto_publish_after_compile
from kb.errors import ValidationError


def _make_minimal_wiki_with_one_page(wiki_dir: Path) -> None:
    """Set up minimal wiki layout so compile_wiki + publish builders have
    something to produce."""
    (wiki_dir / "concepts").mkdir(parents=True, exist_ok=True)
    (wiki_dir / "concepts" / "rag.md").write_text(
        "---\ntitle: RAG\nsource: []\ntype: concept\nconfidence: stated\n"
        "created: 2026-05-03\nupdated: 2026-05-03\n---\n\n"
        "# RAG\n\nRetrieval-augmented generation.\n",
        encoding="utf-8",
    )


def test_auto_publish_emits_four_tier1_formats(tmp_path):
    """AC13: returns dict including llms_txt / llms_full_txt / graph_jsonld /
    sitemap_xml when invoked against a minimal wiki.
    """
    wiki = tmp_path / "wiki"
    _make_minimal_wiki_with_one_page(wiki)

    results = auto_publish_after_compile(wiki)

    expected_formats = {"llms_txt", "llms_full_txt", "graph_jsonld", "sitemap_xml"}
    assert expected_formats.issubset(results.keys()), (
        f"Missing formats: {expected_formats - results.keys()}; got {results.keys()}"
    )

    # Each output file should exist on disk.
    publish_dir = tmp_path / "_publish"
    assert (publish_dir / "llms.txt").exists()
    assert (publish_dir / "llms-full.txt").exists()
    assert (publish_dir / "graph.jsonld").exists()
    assert (publish_dir / "sitemap.xml").exists()


def test_auto_publish_continues_after_per_builder_failure(tmp_path, monkeypatch, caplog):
    """AC13: a failing builder does NOT abort the function; remaining builders
    run + a WARNING is logged.
    """
    wiki = tmp_path / "wiki"
    _make_minimal_wiki_with_one_page(wiki)

    from kb.compile import publish as publish_mod

    def _bad_builder(*args, **kwargs):
        raise OSError("simulated builder failure")

    monkeypatch.setattr(publish_mod, "build_llms_full_txt", _bad_builder)

    import logging

    with caplog.at_level(logging.WARNING):
        results = auto_publish_after_compile(wiki)

    # llms_full_txt should NOT be in results (failed); other formats should.
    assert "llms_full_txt" not in results
    assert "llms_txt" in results
    assert "graph_jsonld" in results
    assert "sitemap_xml" in results
    # WARNING was emitted.
    assert any(
        "auto-publish llms_full_txt failed" in record.message for record in caplog.records
    )


def test_auto_publish_rejects_out_dir_outside_project_root(tmp_path):
    """AC15.5 / M4 mitigation: out_dir outside PROJECT_ROOT is rejected via
    `_validate_path_under_project_root`.

    Reverts: if AC13's `_validate_path_under_project_root` call were removed,
    a malicious out_dir at e.g. `/etc/foo` would proceed to mkdir + write —
    this assertion would fail (ValidationError not raised).
    """
    wiki = tmp_path / "wiki"
    _make_minimal_wiki_with_one_page(wiki)

    # Use an absolute path far outside any plausible PROJECT_ROOT.
    import sys

    if sys.platform == "win32":
        evil_out_dir = Path("C:/Windows/Temp/cycle64_evil_publish")
    else:
        evil_out_dir = Path("/tmp/cycle64_evil_publish")

    with pytest.raises(ValidationError, match="publish_out_dir"):
        auto_publish_after_compile(wiki, out_dir=evil_out_dir)


def test_compile_wiki_invokes_auto_publish_by_default(tmp_path, monkeypatch):
    """AC14: compile_wiki post-success invokes auto_publish_after_compile
    when KB_DISABLE_COMPILE_AUTO_PUBLISH is NOT set.

    Reverts: removing the AC14 try/except block in compile_wiki would leave
    the spy uncalled — test fails.
    """
    monkeypatch.delenv("KB_DISABLE_COMPILE_AUTO_PUBLISH", raising=False)

    wiki = tmp_path / "wiki"
    _make_minimal_wiki_with_one_page(wiki)

    spy_called = 0
    captured_kwargs: list[dict] = []

    def _spy_auto_publish(wiki_dir, *, out_dir=None, incremental=True):
        nonlocal spy_called
        spy_called += 1
        captured_kwargs.append({"wiki_dir": wiki_dir, "incremental": incremental})
        return {}

    from kb.compile import publish as publish_mod

    monkeypatch.setattr(publish_mod, "auto_publish_after_compile", _spy_auto_publish)

    # compile_wiki imports auto_publish_after_compile via local import inside
    # AC14 branch — patch at the publish module's symbol level, plus also
    # the compile_wiki side because it does `from kb.compile.publish import ...`
    # at call time (which captures the current symbol).
    from kb.compile.compiler import compile_wiki

    # Run a minimal compile (no sources to ingest; just exercise the tail).
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(exist_ok=True)
    compile_wiki(wiki_dir=wiki, raw_dir=raw_dir, incremental=True)

    assert spy_called >= 1, (
        f"auto_publish_after_compile NOT called; AC14 hook missing or kill-switch leaked"
    )


def test_kill_switch_env_disables_auto_publish(tmp_path, monkeypatch):
    """AC14: KB_DISABLE_COMPILE_AUTO_PUBLISH=1 read at CALL TIME (per cycle-19
    L2) prevents auto_publish_after_compile invocation.
    """
    monkeypatch.setenv("KB_DISABLE_COMPILE_AUTO_PUBLISH", "1")

    wiki = tmp_path / "wiki"
    _make_minimal_wiki_with_one_page(wiki)

    spy_called = 0

    def _spy_auto_publish(wiki_dir, *, out_dir=None, incremental=True):
        nonlocal spy_called
        spy_called += 1
        return {}

    from kb.compile import publish as publish_mod

    monkeypatch.setattr(publish_mod, "auto_publish_after_compile", _spy_auto_publish)

    from kb.compile.compiler import compile_wiki

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(exist_ok=True)
    compile_wiki(wiki_dir=wiki, raw_dir=raw_dir, incremental=True)

    assert spy_called == 0, (
        f"AC14 kill-switch did NOT prevent auto-publish; spy_called={spy_called}"
    )


def test_compile_wiki_succeeds_even_if_auto_publish_raises(tmp_path, monkeypatch, caplog):
    """AC15: compile_wiki MUST NOT propagate auto-publish failures. The compile
    result returns success; a WARNING is logged.

    Reverts: removing the try/except wrapper around AC14's invocation would
    let the exception propagate — compile_wiki would raise + this assertion
    catches it via pytest.raises (which we don't want here — the OPPOSITE).
    """
    monkeypatch.delenv("KB_DISABLE_COMPILE_AUTO_PUBLISH", raising=False)

    wiki = tmp_path / "wiki"
    _make_minimal_wiki_with_one_page(wiki)

    def _bad_auto_publish(wiki_dir, *, out_dir=None, incremental=True):
        raise RuntimeError("simulated auto-publish failure")

    from kb.compile import publish as publish_mod

    monkeypatch.setattr(publish_mod, "auto_publish_after_compile", _bad_auto_publish)

    import logging

    from kb.compile.compiler import compile_wiki

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(exist_ok=True)
    with caplog.at_level(logging.WARNING):
        # MUST NOT raise — auto-publish failure is isolated.
        result = compile_wiki(wiki_dir=wiki, raw_dir=raw_dir, incremental=True)

    assert result is not None
    assert any(
        "auto-publish skipped" in record.message for record in caplog.records
    ), "Expected 'auto-publish skipped' WARNING in compile_wiki output"


def test_publish_artifacts_outside_wiki_dir_walk(tmp_path):
    """AC13: out_dir defaults to wiki_dir.parent/_publish (sibling of wiki_dir,
    NOT inside it) — keeps publish artifacts out of the page-walk surface.
    """
    wiki = tmp_path / "wiki"
    _make_minimal_wiki_with_one_page(wiki)

    auto_publish_after_compile(wiki)

    publish_dir = tmp_path / "_publish"
    assert publish_dir.exists()
    # Must NOT be inside wiki_dir (would be ingested on next pass).
    assert not (wiki / "_publish").exists()
