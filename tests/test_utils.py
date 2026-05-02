"""Tests for shared utility modules — text, wiki_log, pages, normalize_sources."""

import importlib
import sys
from pathlib import Path

import pytest

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
