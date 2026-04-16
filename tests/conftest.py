"""Shared test fixtures."""

from datetime import date
from pathlib import Path

import pytest

from kb.config import PROJECT_ROOT

WIKI_SUBDIRS = ("entities", "concepts", "comparisons", "summaries", "synthesis")
RAW_SUBDIRS = ("articles", "papers", "repos", "videos", "captures")


@pytest.fixture
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture
def raw_dir(project_root: Path) -> Path:
    return project_root / "raw"


@pytest.fixture
def wiki_dir(project_root: Path) -> Path:
    return project_root / "wiki"


@pytest.fixture
def tmp_wiki(tmp_path: Path) -> Path:
    """Create a temporary wiki directory for isolated tests."""
    wiki = tmp_path / "wiki"
    for subdir in WIKI_SUBDIRS:
        (wiki / subdir).mkdir(parents=True)
    return wiki


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory with wiki/, raw/, and log.md."""
    wiki = tmp_path / "wiki"
    raw = tmp_path / "raw"
    for subdir in WIKI_SUBDIRS:
        (wiki / subdir).mkdir(parents=True)
    for subdir in RAW_SUBDIRS:
        (raw / subdir).mkdir(parents=True)
    (wiki / "log.md").write_text("# Wiki Log\n\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def create_wiki_page(tmp_path: Path):
    """Factory fixture: create a wiki page with proper frontmatter.

    Usage:
        page_path = create_wiki_page(
            "concepts/rag", title="RAG", content="About RAG.", wiki_dir=tmp_wiki)
        page_path = create_wiki_page("entities/openai", page_type="entity", wiki_dir=tmp_wiki)

    H9 fix: wiki_dir is REQUIRED — callers must pass it explicitly to prevent
    silent writes to tmp_path/wiki (a bare tmp_path, not a real wiki fixture).
    """

    def _create(
        page_id: str,
        *,
        title: str | None = None,
        content: str = "",
        source_ref: str = "raw/articles/test.md",
        page_type: str = "concept",
        confidence: str = "stated",
        created: str | None = None,
        updated: str | None = None,
        wiki_dir: Path,
    ) -> Path:
        wiki_dir_actual = wiki_dir
        page_path = wiki_dir_actual / f"{page_id}.md"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        today = date.today().isoformat()
        effective_updated = updated or today
        effective_created = created or updated or today
        page_title = title or page_id.split("/")[-1].replace("-", " ").title()
        fm = (
            f'---\ntitle: "{page_title}"\nsource:\n  - "{source_ref}"\n'
            f"created: {effective_created}\nupdated: {effective_updated}\ntype: {page_type}\n"
            f"confidence: {confidence}\n---\n\n"
        )
        page_path.write_text(fm + content, encoding="utf-8")
        return page_path

    return _create


@pytest.fixture
def create_raw_source(tmp_path: Path):
    """Factory fixture: create a raw source file.

    Usage:
        src_path = create_raw_source("raw/articles/test.md", "Source content here.")
    """

    def _create(
        source_ref: str,
        content: str = "Sample source content.",
        project_dir: Path | None = None,
    ) -> Path:
        assert source_ref.startswith("raw/"), f"source_ref must start with 'raw/': {source_ref}"
        base = project_dir or tmp_path
        source_path = base / source_ref
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(content, encoding="utf-8")
        return source_path

    return _create


_REQUIRED = object()  # sentinel — explicit "must be passed"


@pytest.fixture
def mock_scan_llm(monkeypatch):
    """Install a canned JSON response for call_llm_json inside kb.capture.

    Mock signature mirrors the REAL call_llm_json signature
    (src/kb/utils/llm.py): tier and schema are keyword-only, schema is required.
    The sentinel + assertions catch the bug where capture.py forgets to pass
    schema=_CAPTURE_SCHEMA.
    """

    def _install(
        response: dict,
        expected_schema_keys: tuple[str, ...] = ("items", "filtered_out_count"),
    ):
        def fake_call(prompt, *, tier="write", schema=_REQUIRED, system="", **_kw):
            assert tier == "scan", f"kb_capture must use scan tier, got {tier!r}"
            msg = "kb_capture must pass schema= to call_llm_json"
            assert schema is not _REQUIRED, msg
            assert isinstance(schema, dict), f"schema must be dict, got {type(schema)}"
            for key in expected_schema_keys:
                prop = schema.get("properties", {})
                assert key in prop, f"schema missing property {key!r}"
            required = set(schema.get("required", []))
            missing = required - set(response)
            assert not missing, f"mock response missing required schema keys: {missing}"
            return response

        monkeypatch.setattr("kb.capture.call_llm_json", fake_call)

    return _install


@pytest.fixture
def tmp_captures_dir(tmp_project, monkeypatch):
    """Isolated raw/captures/ with kb.config.CAPTURES_DIR repointed.

    Double monkey-patch defends against import-time vs runtime binding
    (capture.py does `from kb.config import CAPTURES_DIR`).
    """
    captures = tmp_project / "raw" / "captures"
    captures.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("kb.config.CAPTURES_DIR", captures)
    monkeypatch.setattr("kb.capture.CAPTURES_DIR", captures)
    return captures


@pytest.fixture(autouse=False)
def reset_rate_limit():
    """Clear the module-level rate-limit deque before and after each test.

    Shared across test_capture.py and test_mcp_core.py (any test needing a
    clean rate-limit state for kb.capture).
    """
    from kb.capture import _rate_limit_window

    _rate_limit_window.clear()
    yield
    _rate_limit_window.clear()


@pytest.fixture
def patch_all_kb_dir_bindings(monkeypatch, tmp_project):
    """Monkey-patch every module-level RAW_DIR/WIKI_DIR/CAPTURES_DIR binding.

    Required for round-trip integration tests where the cascade path
    (_find_affected_pages → kb.compile.linker, etc.) would otherwise contaminate
    the real wiki/. Enumerates every site explicitly so a NEW binding fails
    loudly rather than silently writing outside tmp_project.

    Spec §9 — verified via:
      grep -rn "from kb.config import.*\\(RAW_DIR\\|WIKI_DIR\\|CAPTURES_DIR\\)" src/kb/
    """
    wiki = tmp_project / "wiki"
    raw = tmp_project / "raw"
    captures = raw / "captures"

    # Ensure directories exist
    wiki.mkdir(parents=True, exist_ok=True)
    (wiki / "summaries").mkdir(exist_ok=True)
    (wiki / "entities").mkdir(exist_ok=True)
    (wiki / "concepts").mkdir(exist_ok=True)
    (wiki / "comparisons").mkdir(exist_ok=True)
    (wiki / "synthesis").mkdir(exist_ok=True)
    raw.mkdir(parents=True, exist_ok=True)
    captures.mkdir(parents=True, exist_ok=True)

    raw_sites = [
        "kb.config.RAW_DIR",
        "kb.ingest.pipeline.RAW_DIR",
        "kb.utils.paths.RAW_DIR",
        "kb.mcp.browse.RAW_DIR",
        "kb.lint.runner.RAW_DIR",
        "kb.review.context.RAW_DIR",
    ]
    wiki_sites = [
        "kb.config.WIKI_DIR",
        "kb.ingest.pipeline.WIKI_DIR",
        "kb.utils.pages.WIKI_DIR",
        "kb.compile.linker.WIKI_DIR",
        "kb.graph.builder.WIKI_DIR",
        "kb.graph.export.WIKI_DIR",
        "kb.review.refiner.WIKI_DIR",
        "kb.review.context.WIKI_DIR",
        "kb.lint.runner.WIKI_DIR",
        "kb.mcp.browse.WIKI_DIR",
        "kb.mcp.app.WIKI_DIR",
    ]
    captures_sites = ["kb.config.CAPTURES_DIR", "kb.capture.CAPTURES_DIR"]

    for site in raw_sites:
        monkeypatch.setattr(site, raw, raising=False)
    for site in wiki_sites:
        monkeypatch.setattr(site, wiki, raising=False)
    for site in captures_sites:
        monkeypatch.setattr(site, captures, raising=False)

    return tmp_project
