"""Tests for shared utility modules — text, wiki_log, pages, normalize_sources."""

import importlib
import logging
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

from kb.utils import wiki_log
from kb.utils.pages import normalize_sources
from kb.utils.text import slugify, yaml_escape
from kb.utils.wiki_log import append_wiki_log

# ── slugify edge cases ────────────────────────────────────────────


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("Hello World", "hello-world"),
        ("  Spaces  and---dashes  ", "spaces-and-dashes"),
        ("CamelCase Test", "camelcase-test"),
        ("special!@#$%chars", "specialchars"),
        ("a", "a"),
        ("UPPER CASE", "upper-case"),
        ("under_score", "under-score"),
        ("multiple   spaces", "multiple-spaces"),
        ("trailing-dash-", "trailing-dash"),
        ("-leading-dash", "leading-dash"),
        ("日本語テスト", "日本語テスト"),  # CJK preserved after dropping re.ASCII (item 11)
        ("mixed 123 numbers", "mixed-123-numbers"),
    ],
)
def test_slugify_parametrized(input_text, expected):
    """slugify handles various text formats correctly."""
    assert slugify(input_text) == expected


# ── yaml_escape edge cases ────────────────────────────────────────


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("normal text", "normal text"),
        ('has "quotes"', 'has \\"quotes\\"'),
        ("has\\backslash", "has\\\\backslash"),
        ("has\nnewline", "has\\nnewline"),
        ("has\ttab", "has\\ttab"),
        ('combo: "quoted\\path\n"', 'combo: \\"quoted\\\\path\\n\\"'),
        ("", ""),
    ],
)
def test_yaml_escape_parametrized(input_text, expected):
    """yaml_escape handles special characters correctly."""
    assert yaml_escape(input_text) == expected


# ── normalize_sources ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "input_val,expected",
    [
        (None, []),
        ([], []),
        ("raw/articles/test.md", ["raw/articles/test.md"]),
        (["raw/a.md", "raw/b.md"], ["raw/a.md", "raw/b.md"]),
    ],
)
def test_normalize_sources(input_val, expected):
    """normalize_sources converts str/None/list to list."""
    assert normalize_sources(input_val) == expected


# ── append_wiki_log ───────────────────────────────────────────────


def test_append_wiki_log_creates_file(tmp_path):
    """append_wiki_log creates log.md if it doesn't exist."""
    log_path = tmp_path / "wiki" / "log.md"
    assert not log_path.exists()

    append_wiki_log("test", "Test message", log_path)

    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    assert "# Wiki Log" in content
    assert "| test | Test message" in content


def test_append_wiki_log_appends_to_existing(tmp_path):
    """append_wiki_log appends to existing log file."""
    log_path = tmp_path / "log.md"
    log_path.write_text("# Wiki Log\n\n- existing entry\n", encoding="utf-8")

    append_wiki_log("ingest", "Ingested foo.md", log_path)

    content = log_path.read_text(encoding="utf-8")
    assert "existing entry" in content
    assert "| ingest | Ingested foo.md" in content


def test_append_wiki_log_requires_log_path(tmp_path):
    """Regression: Phase 4.5 HIGH item H7 (append_wiki_log had optional log_path default)."""
    import pytest

    with pytest.raises(TypeError):
        append_wiki_log("lint", "5 issues found")


def test_append_wiki_log_explicit_path_works(tmp_path):
    """Regression: Phase 4.5 HIGH item H7 — explicit log_path creates and writes log."""
    log_path = tmp_path / "wiki" / "log.md"
    append_wiki_log("ingest", "processed file.md", log_path)
    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    assert "| ingest | processed file.md" in content


# ── load_all_pages ────────────────────────────────────────────────


def test_load_all_pages_empty(tmp_wiki):
    """load_all_pages returns empty list for empty wiki."""
    from kb.utils.pages import load_all_pages

    pages = load_all_pages(tmp_wiki)
    assert pages == []


def test_load_all_pages_returns_all_fields(create_wiki_page, tmp_path):
    """load_all_pages returns dicts with all expected keys."""
    from kb.utils.pages import load_all_pages

    wiki_dir = tmp_path / "wiki"
    create_wiki_page("concepts/rag", content="RAG content.", wiki_dir=wiki_dir)

    pages = load_all_pages(wiki_dir)
    assert len(pages) == 1
    page = pages[0]
    assert set(page.keys()) == {
        "id",
        "path",
        "title",
        "type",
        "confidence",
        "sources",
        "created",
        "updated",
        "content",
        "content_lower",
        # Cycle 14 AC23 + AC1 — additive epistemic-integrity keys
        # (empty string when absent in frontmatter).
        "status",
        "belief_state",
        "authored_by",
    }
    assert page["id"] == "concepts/rag"
    assert page["content_lower"] == page["content"].lower()
    assert isinstance(page["sources"], list)


def test_load_all_pages_normalizes_sources(tmp_path):
    """load_all_pages normalizes source field from str to list."""
    from kb.utils.pages import load_all_pages

    wiki_dir = tmp_path / "wiki"
    page_path = wiki_dir / "concepts" / "test.md"
    page_path.parent.mkdir(parents=True)
    # Write with string source (not list) to test normalization
    page_path.write_text(
        '---\ntitle: "Test"\nsource: "raw/test.md"\n'
        "created: 2026-04-06\nupdated: 2026-04-06\n"
        "type: concept\nconfidence: stated\n---\n\nContent.\n",
        encoding="utf-8",
    )

    pages = load_all_pages(wiki_dir)
    assert len(pages) == 1
    assert pages[0]["sources"] == ["raw/test.md"]


# Cycle 52 fold — cycle-15 AC32 contract regression for load_all_pages
# additive frontmatter keys (status / belief_state / authored_by per
# cycle-14 AC23 + AC1). Source: tests/test_cycle15_load_all_pages_fields.py
# (deleted in same commit). Per cycle-52 design-gate Q4, helper renamed
# _write_page -> _write_concept_page for hygiene-class disambiguation.


def _write_concept_page(wiki_dir: Path, pid: str, extra_fm: str = "") -> Path:
    path = wiki_dir / "concepts" / f"{pid}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""---
title: {pid}
source:
  - raw/articles/{pid}.md
created: 2026-04-20
updated: 2026-04-20
type: concept
confidence: stated
{extra_fm}---
Body.
""",
        encoding="utf-8",
    )
    return path


def test_load_all_pages_emits_authored_by_when_present(tmp_path):
    from kb.utils.pages import load_all_pages

    _write_concept_page(tmp_path, "alpha", extra_fm="authored_by: human\n")
    pages = load_all_pages(tmp_path)
    assert len(pages) == 1
    assert pages[0]["authored_by"] == "human"


def test_load_all_pages_emits_belief_state_when_present(tmp_path):
    from kb.utils.pages import load_all_pages

    _write_concept_page(tmp_path, "beta", extra_fm="belief_state: confirmed\n")
    pages = load_all_pages(tmp_path)
    assert pages[0]["belief_state"] == "confirmed"


def test_load_all_pages_emits_status_when_present(tmp_path):
    """Cycle-14 AC23 regression — status key still surfaces."""
    from kb.utils.pages import load_all_pages

    _write_concept_page(tmp_path, "gamma", extra_fm="status: mature\n")
    pages = load_all_pages(tmp_path)
    assert pages[0]["status"] == "mature"


def test_load_all_pages_emits_all_three_keys_when_present(tmp_path):
    """Cycle-14 L3 atomicity — all three vocabulary keys ship together."""
    from kb.utils.pages import load_all_pages

    _write_concept_page(
        tmp_path,
        "complete",
        extra_fm="authored_by: hybrid\nbelief_state: uncertain\nstatus: developing\n",
    )
    pages = load_all_pages(tmp_path)
    assert pages[0]["authored_by"] == "hybrid"
    assert pages[0]["belief_state"] == "uncertain"
    assert pages[0]["status"] == "developing"


def test_load_all_pages_defaults_empty_string_when_absent(tmp_path):
    """AC32 — missing vocabulary keys default to empty string (additive shape)."""
    from kb.utils.pages import load_all_pages

    _write_concept_page(tmp_path, "minimal")
    pages = load_all_pages(tmp_path)
    assert pages[0]["authored_by"] == ""
    assert pages[0]["belief_state"] == ""
    assert pages[0]["status"] == ""


def test_load_all_pages_keys_are_strings(tmp_path):
    """AC32 — additive keys are always str type (no None/list/dict leakage)."""
    from kb.utils.pages import load_all_pages

    _write_concept_page(tmp_path, "types", extra_fm="authored_by: human\n")
    pages = load_all_pages(tmp_path)
    assert isinstance(pages[0]["authored_by"], str)
    assert isinstance(pages[0]["belief_state"], str)
    assert isinstance(pages[0]["status"], str)


# ── create_wiki_page fixture test ─────────────────────────────────


def test_create_wiki_page_fixture(create_wiki_page, tmp_wiki):
    """create_wiki_page fixture creates valid pages."""
    path = create_wiki_page(
        "entities/openai",
        title="OpenAI",
        content="An AI research company.",
        page_type="entity",
        wiki_dir=tmp_wiki,
    )
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "OpenAI" in content
    assert "type: entity" in content
    assert "raw/articles/test.md" in content


# ── Cycle 11 — page_id + scan_wiki_pages helpers (folded from test_cycle11_utils_pages.py) ─


def test_import_page_id_and_scan_wiki_pages_succeeds():  # noqa: D103
    from kb.utils.pages import page_id, scan_wiki_pages

    assert callable(page_id)
    assert callable(scan_wiki_pages)


def test_graph_builder_re_exports_page_helpers_by_identity():  # noqa: D103
    from kb.graph.builder import page_id as builder_page_id
    from kb.graph.builder import scan_wiki_pages as builder_scan_wiki_pages
    from kb.utils.pages import page_id, scan_wiki_pages

    assert builder_page_id is page_id
    assert builder_scan_wiki_pages is scan_wiki_pages


def test_page_id_returns_lowercase_posix_relative_id():  # noqa: D103
    from kb.utils.pages import page_id

    assert page_id(Path("wiki/concepts/foo.md"), wiki_dir=Path("wiki")) == "concepts/foo"


def test_page_id_lowercases_mixed_case_filename():  # noqa: D103
    from kb.utils.pages import page_id

    assert page_id(Path("wiki/concepts/FOO.md"), wiki_dir=Path("wiki")) == "concepts/foo"


@pytest.mark.skipif(
    sys.platform != "win32",
    reason=(
        "Cycle 36 AC11 — Windows-only backslash-to-POSIX normalisation; "
        "on POSIX, '\\' is a literal filename character."
    ),
)
def test_page_id_normalizes_backslashes_to_posix_id():  # noqa: D103
    from kb.utils.pages import page_id

    assert page_id(Path("wiki\\concepts\\foo.md"), wiki_dir=Path("wiki")) == "concepts/foo"


def test_scan_wiki_pages_returns_sorted_pages_and_skips_root_sentinels(tmp_path):  # noqa: D103
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


def test_private_page_id_alias_is_public_page_id():  # noqa: D103
    from kb.utils.pages import _page_id, page_id

    assert _page_id is page_id


def test_cycle11_ac4_six_callers_resolve_page_helpers_via_canonical_module():
    """Cycle 11 AC4 (R1 fix) — module-level identity check across six callers.

    Walks each caller's module namespace; for any caller exposing page_id /
    scan_wiki_pages, asserts it resolves to the canonical kb.utils.pages
    object. The function-local import path inside compile.compiler is
    covered by test_cycle11_ac4_detect_source_drift_function_local_imports_resolve below.
    """
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
    assert isinstance(report, dict)
    assert "changed_sources" in report or "summary" in report


# ── Phase 4 utils fixes (cycle 56 fold) ───────────────────────────


class TestUtilsFixes:
    """Phase 4 MEDIUM/LOW fixes in utils/ — folded from test_v01001_utils_fixes.py.

    Helper renamed `_write_page` -> `_write_phase4_concept_page` per C52-L4
    uniqueness rule (cycle-52's `_write_concept_page` already lives at line ~190
    of this module).
    """

    @staticmethod
    def _write_phase4_concept_page(dirpath: Path, name: str, body: str) -> None:
        dirpath.mkdir(parents=True, exist_ok=True)
        (dirpath / f"{name}.md").write_text(body, encoding="utf-8")

    def test_load_all_pages_extracts_date_from_datetime(self, tmp_wiki):
        """Page with a full datetime in `updated:` must yield an ISO-8601 date string."""
        import datetime as _dt

        from kb.utils.pages import load_all_pages

        body = (
            "---\n"
            'title: "Foo"\n'
            "type: concept\n"
            "confidence: stated\n"
            "source:\n  - raw/articles/foo.md\n"
            "updated: 2024-01-01 12:00:00\n"
            "---\n"
            "body\n"
        )
        self._write_phase4_concept_page(tmp_wiki / "concepts", "foo", body)
        pages = load_all_pages(tmp_wiki)
        assert len(pages) == 1
        # Must be parseable by date.fromisoformat — no time portion.
        _dt.date.fromisoformat(pages[0]["updated"])
        assert pages[0]["updated"] == "2024-01-01"

    def test_slugify_preserves_version_numbers(self):
        """`v1.0` and `v10` must NOT collide."""
        from kb.utils.text import slugify

        assert slugify("v1.0") != slugify("v10")
        assert slugify("python 3.12") == "python-3-12"
        assert slugify("v1.0") == "v1-0"

    def test_atomic_json_write_cleanup_no_ebadf(self, tmp_path, monkeypatch):
        """When json.dump raises, cleanup must not double-close the fd."""
        import json as _json

        from kb.utils.io import atomic_json_write

        def _boom(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(_json, "dump", _boom)
        with pytest.raises(RuntimeError):
            atomic_json_write({"a": 1}, tmp_path / "out.json")
        # Temp file must be cleaned up.
        assert not any(p.suffix == ".tmp" for p in tmp_path.iterdir())

    def test_extract_wikilinks_strips_embedded_newlines(self):
        """Wikilink targets containing newlines must not produce broken page IDs."""
        from kb.utils.markdown import extract_wikilinks

        text = "See [[foo\nbar]] and [[baz]]."
        links = extract_wikilinks(text)
        for link in links:
            assert "\n" not in link
            assert "\r" not in link

    def test_append_wiki_log_strips_tabs(self, tmp_path):
        """Tab characters in log message must be replaced with spaces."""
        log_path = tmp_path / "log.md"
        log_path.write_text("# Log\n", encoding="utf-8")
        append_wiki_log("ingest", "added\ttabbed\tentry", log_path=log_path)
        content = log_path.read_text(encoding="utf-8")
        # The final line (the log entry) must not contain a literal tab character.
        assert "\t" not in content.splitlines()[-1]


# ── load_purpose + extraction-prompt purpose threading (cycle 57 fold) ──────
#
# Folded from tests/test_v0p5_purpose.py per Step-5 Q3 single-receiver decision
# (feature-coherence over module-coherence — wiki/purpose.md feature touches
# utils/pages + ingest/extractors + query/engine as a coherent capability).
# Receiver test_utils.py is the canonical anchor since `load_purpose` lives in
# `kb.utils.pages`. Cross-layer tests for build_extraction_prompt and
# query_wiki AC14 join here per cycle-55 host-shape preservation (C40-L5).
#
# All 7 bare functions folded verbatim. Module-level imports moved to
# function-local per cycle-19 L2 reload-leak avoidance — receiver test_utils.py
# already has its own imports + load_purpose tests would otherwise create
# an extra module-top dependency on kb.ingest.extractors that bare
# test_utils.py doesn't need.


def test_load_purpose_missing(tmp_path):
    """Returns None when purpose.md does not exist."""
    from kb.utils.pages import load_purpose

    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    assert load_purpose(wiki_dir) is None


def test_load_purpose_returns_content(tmp_path):
    """Returns stripped content when purpose.md exists."""
    from kb.utils.pages import load_purpose

    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    (wiki_dir / "purpose.md").write_text("# KB Purpose\n\nGoals: test.\n", encoding="utf-8")
    result = load_purpose(wiki_dir)
    assert result == "# KB Purpose\n\nGoals: test."


def test_load_purpose_empty_file(tmp_path):
    """Returns None when purpose.md exists but is empty."""
    from kb.utils.pages import load_purpose

    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    (wiki_dir / "purpose.md").write_text("   \n", encoding="utf-8")
    assert load_purpose(wiki_dir) is None


def test_h8_load_purpose_reads_from_wiki_dir_not_production(tmp_path):
    """Regression: Phase 4.5 HIGH item H8 (load_purpose always read production wiki/purpose.md)."""
    from kb.config import WIKI_DIR as prod_wiki_dir
    from kb.utils.pages import load_purpose

    tmp_wiki = tmp_path / "wiki"
    tmp_wiki.mkdir()
    (tmp_wiki / "purpose.md").write_text("# Test Purpose\n\nThis is the test KB.", encoding="utf-8")

    # Should read from tmp_wiki, not from the production WIKI_DIR
    result = load_purpose(tmp_wiki)
    assert result is not None
    assert "Test Purpose" in result

    # Production purpose.md should NOT have been read (we'd get its content instead)
    prod_purpose = prod_wiki_dir / "purpose.md"
    if prod_purpose.exists():
        prod_content = prod_purpose.read_text(encoding="utf-8").strip()
        assert result != prod_content or "Test Purpose" in prod_content, (
            "H8: load_purpose(wiki_dir) returned production purpose.md instead of tmp_wiki"
        )


def test_extraction_prompt_includes_purpose():
    """Purpose text is injected into extraction prompt when provided."""
    from kb.ingest.extractors import build_extraction_prompt

    template = {
        "name": "article",
        "description": "A web article",
        "extract": ["title: string", "key_claims: list of strings"],
    }
    prompt = build_extraction_prompt("Some content.", template, purpose="Focus on LLM systems.")
    assert "KB FOCUS" in prompt
    assert "Focus on LLM systems." in prompt


def test_extraction_prompt_no_purpose():
    """Extraction prompt has no KB FOCUS section when purpose is None."""
    from kb.ingest.extractors import build_extraction_prompt

    template = {
        "name": "article",
        "description": "A web article",
        "extract": ["title: string"],
    }
    prompt = build_extraction_prompt("Some content.", template, purpose=None)
    assert "KB FOCUS" not in prompt


def test_extraction_prompt_purpose_before_source_type():
    """Purpose section appears before 'Source type:' in the prompt."""
    from kb.ingest.extractors import build_extraction_prompt

    template = {
        "name": "article",
        "description": "A web article",
        "extract": ["title: string"],
    }
    prompt = build_extraction_prompt("Some content.", template, purpose="Goal: test.")
    focus_idx = prompt.index("KB FOCUS")
    source_type_idx = prompt.index("Source type:")
    assert focus_idx < source_type_idx


# ── Cycle 17 AC14 — purpose threads into query_wiki synthesis prompt ───────


def test_cycle17_ac14_query_wiki_threads_purpose_to_synthesis_prompt(tmp_path, monkeypatch):
    """AC14 — purpose.md text threads into the synthesis prompt via query_wiki.

    Cycle 6 shipped a rewriter-side test pinning KB_FOCUS reaches rewrite_query.
    Cycle 17 AC14 closes the query-side gap: on the API / hybrid-synthesis
    path, `query_wiki(wiki_dir=tmp)` must pass `purpose.md` content through
    to the synthesizer's call_llm invocation.
    """
    import kb.utils.pages as pages_module
    from kb.query import engine as query_engine

    tmp_wiki = tmp_path / "wiki"
    tmp_wiki.mkdir()
    marker = "CYCLE17_AC14_PURPOSE_MARKER_deadbeef"
    (tmp_wiki / "purpose.md").write_text(
        f"# KB Purpose\n\n{marker}\n\nFocus on cycle 17 regression coverage.\n",
        encoding="utf-8",
    )
    # Seed one page so search_pages returns a non-empty result — the synthesis
    # path only fires when there's something to synthesise.
    (tmp_wiki / "entities").mkdir()
    (tmp_wiki / "entities" / "seeder.md").write_text(
        "---\ntitle: Seeder\ntype: entity\nconfidence: stated\n"
        "source:\n  - raw/articles/seeder.md\n---\n\nContent about seeder.",
        encoding="utf-8",
    )

    # Clear the LRU cache on load_purpose so the new purpose.md is read.
    pages_module.load_purpose.cache_clear()

    captured_prompts: list[str] = []

    def spy_call_llm(prompt, tier="write", **kwargs):
        captured_prompts.append(prompt)
        return "synthesised answer"

    monkeypatch.setattr(query_engine, "call_llm", spy_call_llm)

    # Invoke the API synthesis branch by passing the wiki_dir.
    # query_wiki in API mode calls load_purpose(wiki_dir) then threads the
    # returned text into the synthesis prompt via call_llm.
    try:
        query_engine.query_wiki("What is the seeder?", wiki_dir=tmp_wiki)
    except Exception:
        # Any LLM-path exception is OK — we only care that call_llm was
        # invoked with the marker in its prompt.
        pass

    # Assert the marker reached the synthesis prompt.
    assert captured_prompts, "AC14: call_llm never invoked under query_wiki(wiki_dir=tmp)"
    joined = "\n".join(captured_prompts)
    assert marker in joined, (
        f"AC14 regression: purpose.md marker {marker!r} did not thread into "
        f"the synthesis prompt. Captured prompts:\n{joined[:2000]}"
    )


def test_cycle17_ac18_load_purpose_ignores_kb_project_root_env(tmp_path, monkeypatch):
    """AC18 regression pin — load_purpose(wiki_dir=tmp) ignores KB_PROJECT_ROOT env.

    Cycle 4 item #28 already removed the PROJECT_ROOT fallback from
    load_purpose. This test pins the invariant so a future refactor that
    re-introduces a `KB_PROJECT_ROOT` env-var fallback inside `load_purpose`
    triggers a red-line test failure.
    """
    import kb.utils.pages as pages_module

    # Set the env var to a directory that contains a DIFFERENT purpose.md.
    elsewhere = tmp_path / "elsewhere" / "wiki"
    elsewhere.mkdir(parents=True)
    (elsewhere / "purpose.md").write_text("POISON_PURPOSE_FROM_ENV", encoding="utf-8")
    monkeypatch.setenv("KB_PROJECT_ROOT", str(tmp_path / "elsewhere"))

    # Real tmp_wiki that the caller passes.
    tmp_wiki = tmp_path / "real_wiki"
    tmp_wiki.mkdir()
    expected = "REAL_CALLER_PROVIDED_PURPOSE"
    (tmp_wiki / "purpose.md").write_text(expected, encoding="utf-8")

    pages_module.load_purpose.cache_clear()
    result = pages_module.load_purpose(tmp_wiki)
    assert result == expected, (
        f"AC18 regression: load_purpose returned {result!r} instead of the "
        f"caller-provided content {expected!r}. A KB_PROJECT_ROOT-based "
        f"fallback may have been re-introduced — check utils/pages.py::load_purpose."
    )
    # Also verify the poisoned path was NOT read.
    assert "POISON_PURPOSE_FROM_ENV" not in (result or "")


# ── wiki_log rotation (cycle 58 fold) ─────────────────────────────
# Folded from `tests/test_cycle18_wiki_log.py` — rotate-in-lock + generic
# helper tests. Threat T2 (cycle 18): POSIX handle-holding-stale-file race.
# Rotation must run INSIDE `file_lock(log_path)` so a concurrent appender
# cannot write to the renamed-away (archived) file.


def test_rotate_inside_lock(tmp_path: Path, monkeypatch) -> None:
    """AC4 + AC6 — rotate runs after file_lock.__enter__ and before append write."""
    log_path = tmp_path / "log.md"
    # Populate the log to exceed the rotation threshold so rotate actually fires.
    log_path.write_text(
        "# Wiki Log\n\n" + ("x" * (wiki_log.LOG_SIZE_WARNING_BYTES + 100)),
        encoding="utf-8",
    )

    events: list[str] = []

    # Spy on file_lock — record enter/exit order around the inner write.
    @contextmanager
    def spy_file_lock(path: Path, timeout=None):
        events.append(f"lock_enter:{path.name}")
        try:
            yield
        finally:
            events.append(f"lock_exit:{path.name}")

    # Spy on rotate — record when it runs relative to lock boundaries.
    real_rotate = wiki_log._rotate_log_if_oversized

    def spy_rotate(p: Path) -> None:
        events.append(f"rotate:{p.name}")
        real_rotate(p)

    # Spy on the rotation promote. Cycle 87 R1 (MINOR-3) routed rotation through
    # the shared barrier and R2 (MINOR-5) settled on the NO-CLOBBER variant, so
    # `Path.rename` no longer fires here — and on Windows the promote is
    # `MoveFileExW`, so `os.replace` would not fire either. The shared helper is
    # the only platform-agnostic seam.
    real_promote = wiki_log.durable_rename

    def spy_rename(src, target):
        events.append(f"rename:{Path(src).name}->{Path(target).name}")
        return real_promote(src, target)

    monkeypatch.setattr(wiki_log, "file_lock", spy_file_lock)
    monkeypatch.setattr(wiki_log, "_rotate_log_if_oversized", spy_rotate)
    monkeypatch.setattr(wiki_log, "durable_rename", spy_rename)

    wiki_log.append_wiki_log("test", "trigger rotate", log_path)

    # Assert the TOTAL ORDER: lock_enter < rotate < rename < lock_exit.
    lock_enter_idx = next(i for i, e in enumerate(events) if e.startswith("lock_enter"))
    rotate_idx = next(i for i, e in enumerate(events) if e.startswith("rotate:"))
    rename_idx = next(i for i, e in enumerate(events) if e.startswith("rename:"))
    lock_exit_idx = next(i for i, e in enumerate(events) if e.startswith("lock_exit"))

    assert lock_enter_idx < rotate_idx, f"Rotate must run AFTER lock_enter. Events: {events}"
    assert rotate_idx < rename_idx, f"Rename must run AFTER rotate call. Events: {events}"
    assert rename_idx < lock_exit_idx, f"Rename must run BEFORE lock_exit. Events: {events}"


def test_rotate_if_oversized_generic(tmp_path: Path, caplog) -> None:
    """AC5 — generic helper rotates a non-log.md path with the right archive suffix."""
    path = tmp_path / "foo.jsonl"
    path.write_text("x" * 200, encoding="utf-8")

    with caplog.at_level(logging.INFO, logger="kb.utils.wiki_log"):
        wiki_log.rotate_if_oversized(path, max_bytes=100, archive_stem_prefix="foo")

    # Original path gone, archive created with .jsonl suffix preserved.
    assert not path.exists()
    archives = list(tmp_path.glob("foo.*.jsonl"))
    assert len(archives) == 1, f"Expected 1 archive, got {archives}"
    # Audit event fires BEFORE the rename — rename wipes mtime, but the log record
    # in caplog is the evidence.
    rotate_records = [r for r in caplog.records if "Rotating" in r.getMessage()]
    assert len(rotate_records) == 1, f"Expected 1 rotation log line, got {rotate_records}"


def test_rotate_if_oversized_under_threshold(tmp_path: Path) -> None:
    """AC5 — no rotation when file size <= max_bytes."""
    path = tmp_path / "foo.jsonl"
    path.write_text("x" * 50, encoding="utf-8")

    wiki_log.rotate_if_oversized(path, max_bytes=100, archive_stem_prefix="foo")

    assert path.exists(), "File must still exist after no-op rotation"
    assert list(tmp_path.glob("foo.*.jsonl")) == [], "No archive expected under threshold"


def test_rotate_if_oversized_missing_file(tmp_path: Path) -> None:
    """AC5 — no-op for non-existent path."""
    path = tmp_path / "missing.jsonl"
    wiki_log.rotate_if_oversized(path, max_bytes=100, archive_stem_prefix="missing")
    assert not path.exists()


def test_rotate_if_oversized_ordinal_collision(tmp_path: Path) -> None:
    """AC5 — second rotation in the same month uses ordinal .2 fallback."""
    from datetime import UTC, datetime  # noqa: PLC0415

    year_month = datetime.now(UTC).strftime("%Y-%m")
    stem = f"foo.{year_month}"
    # Pre-seed the primary archive name so the helper must pick the .2 ordinal.
    (tmp_path / f"{stem}.jsonl").write_text("pre-existing", encoding="utf-8")

    path = tmp_path / "foo.jsonl"
    path.write_text("x" * 200, encoding="utf-8")

    wiki_log.rotate_if_oversized(path, max_bytes=100, archive_stem_prefix="foo")

    assert not path.exists()
    assert (tmp_path / f"{stem}.jsonl").read_text(encoding="utf-8") == "pre-existing"
    assert (tmp_path / f"{stem}.2.jsonl").exists(), (
        f"Expected ordinal .2 archive; got {list(tmp_path.iterdir())}"
    )


# ═══════════════════════════════════════════════════════════════════════
# Cycle 78 freeze-and-fold — moved verbatim from tests/test_v0916_task02.py
# (utils/pages.py parts). No deviations.
# ═══════════════════════════════════════════════════════════════════════


class TestLoadAllPagesIntTitle:
    """load_all_pages must coerce integer titles to strings."""

    def test_integer_title_coerced_to_string(self, tmp_wiki):
        page = tmp_wiki / "concepts" / "year-2024.md"
        page.write_text(
            "---\ntitle: 2024\nsource: []\ncreated: 2026-01-01\n"
            "updated: 2026-01-01\ntype: concept\nconfidence: stated\n---\n\n"
            "Content about 2024.\n",
            encoding="utf-8",
        )

        from kb.utils.pages import load_all_pages

        pages = load_all_pages(tmp_wiki)
        assert len(pages) == 1
        assert isinstance(pages[0]["title"], str)
        assert pages[0]["title"] == "2024"


class TestNormalizeSources:
    """normalize_sources edge cases."""

    def test_empty_string_filtered(self):
        from kb.utils.pages import normalize_sources

        assert normalize_sources("") == []

    def test_list_with_empty_string_filtered(self):
        from kb.utils.pages import normalize_sources

        result = normalize_sources(["raw/a.md", "", "raw/b.md"])
        assert "" not in result
        assert len(result) == 2
