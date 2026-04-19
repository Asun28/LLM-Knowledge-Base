"""Shared test fixtures."""

import sys
from datetime import date
from pathlib import Path

import pytest

from kb.config import PROJECT_ROOT, SOURCE_TYPE_DIRS

WIKI_SUBDIRS = ("entities", "concepts", "comparisons", "summaries", "synthesis")
RAW_SUBDIRS = tuple(sorted(d.name for d in SOURCE_TYPE_DIRS.values()))

_TMP_KB_ENV_PATCHED_NAMES = (
    "PROJECT_ROOT",
    "RAW_DIR",
    "WIKI_DIR",
    "CAPTURES_DIR",
    "OUTPUTS_DIR",
    "VERDICTS_PATH",
    "FEEDBACK_PATH",
    "REVIEW_HISTORY_PATH",
    "WIKI_ENTITIES",
    "WIKI_CONCEPTS",
    "WIKI_COMPARISONS",
    "WIKI_SUMMARIES",
    "WIKI_SYNTHESIS",
    "RAW_ARTICLES",
    "RAW_PAPERS",
    "RAW_REPOS",
    "RAW_VIDEOS",
    "RAW_PODCASTS",
    "RAW_BOOKS",
    "RAW_DATASETS",
    "RAW_CONVERSATIONS",
    "RAW_ASSETS",
    "SOURCE_TYPE_DIRS",
)


# Cycle 7 AC1 — autouse reset of embeddings module singletons to prevent
# order-dependent test failures. `_model` and `_index_cache` live at module
# scope in kb.query.embeddings; without this fixture, tests that touch the
# vector index leak state into every subsequent test in the collection order.
# Lazy-imports to avoid forcing the dep on tests that don't touch embeddings.
@pytest.fixture(autouse=True)
def _reset_embeddings_state():
    """Reset kb.query.embeddings module singletons between every test."""
    try:
        import kb.query.embeddings as _emb  # noqa: PLC0415

        _emb._reset_model()
    except ImportError:
        pass  # embeddings optional — skip if deps missing
    yield
    try:
        import kb.query.embeddings as _emb  # noqa: PLC0415

        _emb._reset_model()
    except ImportError:
        pass


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
    (wiki / "index.md").write_text(
        "---\n"
        "title: Wiki Index\n"
        "source: []\n"
        "type: index\n"
        "---\n\n"
        "# Knowledge Base Index\n\n"
        "## Pages\n\n"
        "*No pages yet.*\n\n"
        "## Entities\n\n"
        "*No pages yet.*\n\n"
        "## Concepts\n\n"
        "*No pages yet.*\n\n"
        "## Comparisons\n\n"
        "*No pages yet.*\n\n"
        "## Summaries\n\n"
        "*No pages yet.*\n\n"
        "## Synthesis\n\n"
        "*No pages yet.*\n",
        encoding="utf-8",
    )
    (wiki / "_sources.md").write_text(
        "---\ntitle: Source Mapping\nsource: []\ntype: index\n---\n\n# Source Mapping\n",
        encoding="utf-8",
    )
    (wiki / "log.md").write_text("# Wiki Log\n\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def tmp_kb_env(tmp_path: Path, monkeypatch) -> Path:
    """Patch KB paths into a temporary project.

    Patched names: PROJECT_ROOT, RAW_DIR, WIKI_DIR, CAPTURES_DIR, OUTPUTS_DIR,
    VERDICTS_PATH, FEEDBACK_PATH, REVIEW_HISTORY_PATH, WIKI_ENTITIES,
    WIKI_CONCEPTS, WIKI_COMPARISONS, WIKI_SUMMARIES, WIKI_SYNTHESIS,
    WIKI_INDEX, WIKI_SOURCES, WIKI_LOG, WIKI_CONTRADICTIONS, WIKI_PURPOSE,
    RAW_ARTICLES, RAW_PAPERS, RAW_REPOS, RAW_VIDEOS, RAW_PODCASTS, RAW_BOOKS,
    RAW_DATASETS, RAW_CONVERSATIONS, RAW_ASSETS, SOURCE_TYPE_DIRS.

    Also patches kb.capture._CAPTURES_DIR_RESOLVED, kb.capture._captures_resolved,
    and kb.capture._project_resolved when kb.capture is already imported.

    DELIBERATELY EXCLUDED (read-only package data, never written by kb):
    TEMPLATES_DIR (YAML extraction templates shipped in repo); RESEARCH_DIR
    (human-authored analysis). Tests that need tmp templates/research must
    monkeypatch those explicitly.

    Update this fixture when new kb.config WRITE-TARGET path constants or
    derived path caches are added.
    """
    import kb.config as config  # noqa: PLC0415

    project = tmp_path
    raw = project / "raw"
    wiki = project / "wiki"
    data = project / ".data"
    captures = raw / "captures"

    patched = {
        "PROJECT_ROOT": project,
        "RAW_DIR": raw,
        "WIKI_DIR": wiki,
        "CAPTURES_DIR": captures,
        "OUTPUTS_DIR": project / "outputs",
        "VERDICTS_PATH": data / "lint_verdicts.json",
        "FEEDBACK_PATH": data / "query_feedback.json",
        "REVIEW_HISTORY_PATH": data / "review_history.json",
        "WIKI_ENTITIES": wiki / "entities",
        "WIKI_CONCEPTS": wiki / "concepts",
        "WIKI_COMPARISONS": wiki / "comparisons",
        "WIKI_SUMMARIES": wiki / "summaries",
        "WIKI_SYNTHESIS": wiki / "synthesis",
        "WIKI_INDEX": wiki / "index.md",
        "WIKI_SOURCES": wiki / "_sources.md",
        "WIKI_LOG": wiki / "log.md",
        "WIKI_CONTRADICTIONS": wiki / "contradictions.md",
        "WIKI_PURPOSE": wiki / "purpose.md",
        "RAW_ARTICLES": raw / "articles",
        "RAW_PAPERS": raw / "papers",
        "RAW_REPOS": raw / "repos",
        "RAW_VIDEOS": raw / "videos",
        "RAW_PODCASTS": raw / "podcasts",
        "RAW_BOOKS": raw / "books",
        "RAW_DATASETS": raw / "datasets",
        "RAW_CONVERSATIONS": raw / "conversations",
        "RAW_ASSETS": raw / "assets",
    }
    original_values = {name: getattr(config, name) for name in patched}
    original_source_type_dirs = config.SOURCE_TYPE_DIRS
    patched_source_type_dirs = {
        source_type: raw / source_dir.name
        for source_type, source_dir in original_source_type_dirs.items()
    }
    patched["SOURCE_TYPE_DIRS"] = patched_source_type_dirs
    original_values["SOURCE_TYPE_DIRS"] = original_source_type_dirs

    for path in (
        wiki,
        raw,
        data,
        patched["OUTPUTS_DIR"],
        captures,
        patched["WIKI_ENTITIES"],
        patched["WIKI_CONCEPTS"],
        patched["WIKI_COMPARISONS"],
        patched["WIKI_SUMMARIES"],
        patched["WIKI_SYNTHESIS"],
        patched["RAW_ARTICLES"],
        patched["RAW_PAPERS"],
        patched["RAW_REPOS"],
        patched["RAW_VIDEOS"],
        patched["RAW_PODCASTS"],
        patched["RAW_BOOKS"],
        patched["RAW_DATASETS"],
        patched["RAW_CONVERSATIONS"],
        patched["RAW_ASSETS"],
    ):
        path.mkdir(parents=True, exist_ok=True)

    for name, value in patched.items():
        monkeypatch.setattr(config, name, value)

    # Mirror already-imported `from kb.config import X` bindings that still
    # point at the original config objects. Scoped to ``kb.*`` modules so a
    # third-party module happening to hold a dict/Path that compares equal
    # cannot be rebound — cycle-12 R1 architect review hardening.
    for module_name, module in tuple(sys.modules.items()):
        if module is None:
            continue
        if not (module_name == "kb" or module_name.startswith("kb.")):
            continue
        for name, value in patched.items():
            if getattr(module, name, object()) == original_values[name]:
                monkeypatch.setattr(module, name, value, raising=False)

    capture_module = sys.modules.get("kb.capture")
    if capture_module is not None:
        monkeypatch.setattr(capture_module, "_CAPTURES_DIR_RESOLVED", captures.resolve())
        monkeypatch.setattr(capture_module, "_captures_resolved", captures.resolve())
        monkeypatch.setattr(capture_module, "_project_resolved", project.resolve())

    return project


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
    assert captures.resolve().is_relative_to(tmp_project.resolve()), (
        f"tmp_captures_dir escaped tmp_project: {captures} not under {tmp_project}"
    )
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
