"""Shared test fixtures."""

import sys
from datetime import date
from pathlib import Path

import pytest

from kb.config import PROJECT_ROOT, SOURCE_TYPE_DIRS

# Cycle 64 AC2 — captured at module import time, before any test or fixture
# can monkeypatch kb.config. Used by `real_project_root` fixture to yield the
# genuine repo path under `pytest --use-real-paths` opt-in.
_REAL_PROJECT_ROOT_AT_CONFTEST_IMPORT = Path(PROJECT_ROOT)

WIKI_SUBDIRS = ("entities", "concepts", "comparisons", "summaries", "synthesis")
RAW_SUBDIRS = tuple(sorted(d.name for d in SOURCE_TYPE_DIRS.values()))


# Cycle 64 AC2 — pytest CLI option for opting OUT of the autouse sandbox.
# Tests that genuinely need the real repo paths (rare; should be a small
# minority) request the `real_project_root` fixture and the test author
# invokes pytest with `--use-real-paths`.
def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--use-real-paths",
        action="store_true",
        default=False,
        help=(
            "Cycle 64 AC2: opt out of conftest's autouse sandbox so the "
            "`real_project_root` fixture yields the genuine repo PROJECT_ROOT. "
            "Without this flag, `real_project_root` raises RuntimeError. "
            "The autouse `tmp_kb_env` fixture still runs (sandbox is in effect "
            "for tests that don't request `real_project_root`)."
        ),
    )

_TMP_KB_ENV_PATCHED_NAMES = (
    "PROJECT_ROOT",
    "RAW_DIR",
    "WIKI_DIR",
    "CAPTURES_DIR",
    "OUTPUTS_DIR",
    "VERDICTS_PATH",
    "FEEDBACK_PATH",
    "REVIEW_HISTORY_PATH",
    "HASH_MANIFEST",  # cycle 18 AC1 — lives on kb.compile.compiler, not kb.config (see tmp_kb_env)
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
    """Return the ACTIVE kb.config.PROJECT_ROOT (sandbox-aware after cycle 64 AC1).

    Under the autouse `tmp_kb_env` fixture, this returns the per-test tmp_path
    sandbox. Tests that genuinely need the real repo path must request
    `real_project_root` and run pytest with `--use-real-paths`.

    Cycle 64 AC1: lookup is at CALL TIME via the kb.config module attribute,
    not bound at conftest import time. This ensures the autouse monkeypatch
    on `kb.config.PROJECT_ROOT` is visible through this fixture.
    """
    import kb.config as config  # noqa: PLC0415

    return config.PROJECT_ROOT


@pytest.fixture
def raw_dir(project_root: Path) -> Path:
    return project_root / "raw"


@pytest.fixture
def wiki_dir(project_root: Path) -> Path:
    return project_root / "wiki"


@pytest.fixture
def real_project_root(request: pytest.FixtureRequest) -> Path:
    """Cycle 64 AC2 — opt-in fixture yielding the genuine repo PROJECT_ROOT.

    Raises RuntimeError if `pytest --use-real-paths` was NOT passed. This
    enforces a single-CLI-flag global escape hatch so tests that read or
    write to the live wiki tree are explicit about it (not silently leaked
    via the default `project_root` / `wiki_dir` / `raw_dir` fixtures, which
    are sandbox-aware after AC1).

    Tests requesting this fixture should be exceedingly rare. Most tests
    should use `tmp_wiki` / `tmp_project` / `tmp_kb_env` (autouse) for
    sandboxed paths.
    """
    if not request.config.getoption("--use-real-paths"):
        raise RuntimeError(
            "real_project_root requires --use-real-paths to opt out of "
            "conftest sandboxing; see tests/conftest.py "
            "(cycle 64 AC2 / project_cycle61_mimo_failure context)"
        )
    return _REAL_PROJECT_ROOT_AT_CONFTEST_IMPORT


@pytest.fixture
def tmp_wiki(tmp_path: Path) -> Path:
    """Create a temporary wiki directory for isolated tests.

    Cycle 64 AC1: the autouse `tmp_kb_env` fixture also creates these
    subdirs under the same tmp_path; mkdir uses ``exist_ok=True`` so
    requesting both fixtures (or relying on autouse alone) is idempotent.
    """
    wiki = tmp_path / "wiki"
    for subdir in WIKI_SUBDIRS:
        (wiki / subdir).mkdir(parents=True, exist_ok=True)
    return wiki


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory with wiki/, raw/, and log.md.

    Cycle 64 AC1: idempotent under autouse `tmp_kb_env` (which pre-creates
    most of these subdirs).
    """
    wiki = tmp_path / "wiki"
    raw = tmp_path / "raw"
    for subdir in WIKI_SUBDIRS:
        (wiki / subdir).mkdir(parents=True, exist_ok=True)
    for subdir in RAW_SUBDIRS:
        (raw / subdir).mkdir(parents=True, exist_ok=True)
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


def _apply_kb_path_patches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    mkdir: bool,
) -> Path:
    """Cycle 64 AC1 helper: patch kb.config WIKI_* / RAW_* / PROJECT_ROOT to
    a per-test ``tmp_path`` sandbox.

    Two callers:
    - The autouse `_autouse_kb_path_sandbox` fixture invokes with ``mkdir=False``
      so tests that do their own `tmp_path/raw/articles.mkdir(parents=True)`
      etc. don't collide with redundant directory creation.
    - The explicit `tmp_kb_env` fixture (and `kb_sandbox` / `_kb_sandbox`
      aliases) invokes with ``mkdir=True`` to preserve the cycle 12+ contract
      that requesting `tmp_kb_env` produces a fully-built project tree —
      230+ existing call sites depend on this.

    The patching half is idempotent: running both fixtures for one test
    (autouse + explicit request) just re-applies the same setattr to the
    same paths, and the mirror-rebind loop's equality check skips the
    second pass cleanly.
    """
    import kb.compile.compiler as compiler  # noqa: PLC0415
    import kb.config as config  # noqa: PLC0415

    project = tmp_path
    raw = project / "raw"
    wiki = project / "wiki"
    data = project / ".data"
    captures = raw / "captures"
    hash_manifest_path = data / "hashes.json"  # cycle 18 AC2 — compiler-scoped

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

    if mkdir:
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

    # Cycle 18 AC2 — HASH_MANIFEST is a kb.compile.compiler attribute, not a
    # kb.config attribute. Patch it separately after the config loop so the
    # getattr(config, name) in the original_values build above does not trip.
    original_hash_manifest = compiler.HASH_MANIFEST
    monkeypatch.setattr(compiler, "HASH_MANIFEST", hash_manifest_path)

    # Build the mirror-rebind map that covers both config-scoped patches AND
    # the compiler-scoped HASH_MANIFEST so already-imported `kb.*.HASH_MANIFEST`
    # bindings get the tmp path too.
    mirror_patched: dict = dict(patched)
    mirror_patched["HASH_MANIFEST"] = hash_manifest_path
    mirror_original: dict = dict(original_values)
    mirror_original["HASH_MANIFEST"] = original_hash_manifest

    # Mirror already-imported `from kb.config import X` bindings that still
    # point at the original config objects. Scoped to ``kb.*`` modules so a
    # third-party module happening to hold a dict/Path that compares equal
    # cannot be rebound — cycle-12 R1 architect review hardening.
    for module_name, module in tuple(sys.modules.items()):
        if module is None:
            continue
        if not (module_name == "kb" or module_name.startswith("kb.")):
            continue
        for name, value in mirror_patched.items():
            if getattr(module, name, object()) == mirror_original[name]:
                monkeypatch.setattr(module, name, value, raising=False)

    capture_module = sys.modules.get("kb.capture")
    if capture_module is not None:
        monkeypatch.setattr(capture_module, "_CAPTURES_DIR_RESOLVED", captures.resolve())
        monkeypatch.setattr(capture_module, "_captures_resolved", captures.resolve())
        monkeypatch.setattr(capture_module, "_project_resolved", project.resolve())

    # Cycle 17 AC16 / design gate Q3 — clear every production `@lru_cache`
    # keyed on a path or source-type so the fixture's new sandbox paths are
    # read fresh. Without this, a prior test's cached `load_purpose(other_wiki)`
    # could survive into this test if keys happen to collide (they shouldn't,
    # but the fixture's documented contract is "production sees tmp paths"
    # and a stale-cache leak would violate that contract silently).
    for cached_callable_path in (
        "kb.utils.pages.load_purpose",
        "kb.ingest.extractors._load_template_cached",
        "kb.ingest.extractors._build_schema_cached",
    ):
        module_name, _, attr = cached_callable_path.rpartition(".")
        mod = sys.modules.get(module_name)
        if mod is None:
            continue
        func = getattr(mod, attr, None)
        if func is None:
            continue
        cache_clear = getattr(func, "cache_clear", None)
        if callable(cache_clear):
            cache_clear()

    return project


@pytest.fixture(autouse=True)
def _autouse_kb_path_sandbox(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    """Cycle 64 AC1 — autouse sandbox: patch `kb.config.WIKI_*` / `RAW_*` /
    `PROJECT_ROOT` to per-test ``tmp_path`` so production code reading those
    constants does not see the developer's real wiki tree by default.

    No mkdir — tests that need the project tree pre-built request the
    explicit `tmp_kb_env` (or `kb_sandbox`) fixture, which adds mkdir on top.
    Tests that build their own subtree under `tmp_path` are unaffected by
    autouse mkdir collisions.

    Opt out via `pytest --use-real-paths` (cycle 64 AC2). Under that flag,
    the autouse fixture early-returns and `kb.config.*` is not monkeypatched.
    """
    if request.config.getoption("--use-real-paths"):
        return
    _apply_kb_path_patches(tmp_path, monkeypatch, mkdir=False)


@pytest.fixture
def tmp_kb_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> Path:
    """Patch KB paths into a temporary project AND build the directory tree.

    Patched names (set by `_apply_kb_path_patches`): PROJECT_ROOT, RAW_DIR,
    WIKI_DIR, CAPTURES_DIR, OUTPUTS_DIR, VERDICTS_PATH, FEEDBACK_PATH,
    REVIEW_HISTORY_PATH, HASH_MANIFEST, WIKI_ENTITIES, WIKI_CONCEPTS,
    WIKI_COMPARISONS, WIKI_SUMMARIES, WIKI_SYNTHESIS, WIKI_INDEX, WIKI_SOURCES,
    WIKI_LOG, WIKI_CONTRADICTIONS, WIKI_PURPOSE, RAW_ARTICLES, RAW_PAPERS,
    RAW_REPOS, RAW_VIDEOS, RAW_PODCASTS, RAW_BOOKS, RAW_DATASETS,
    RAW_CONVERSATIONS, RAW_ASSETS, SOURCE_TYPE_DIRS.

    Cycle 18 AC1/AC2 — HASH_MANIFEST lives on `kb.compile.compiler`, not
    `kb.config`. Patched separately. `tests.*` modules that import
    HASH_MANIFEST at module top before this fixture runs are NOT covered
    by the mirror-rebind loop; use `monkeypatch.setattr` in the test itself.

    Also patches `kb.capture._CAPTURES_DIR_RESOLVED`, `_captures_resolved`,
    `_project_resolved` when `kb.capture` is already imported.

    DELIBERATELY EXCLUDED (read-only package data, never written by kb):
    TEMPLATES_DIR (YAML extraction templates shipped in repo); RESEARCH_DIR
    (human-authored analysis). Tests that need tmp templates/research must
    monkeypatch those explicitly.

    Update `_apply_kb_path_patches` (above) when new `kb.config` write-target
    path constants or derived path caches are added.

    Cycle 64 AC1: behaviour preserved for explicit-fixture callers. Autouse
    sandbox `_autouse_kb_path_sandbox` runs first (patch only); this fixture
    re-applies the same patches AND mkdirs the project tree so existing
    callers keep their pre-built directories.
    """
    if request.config.getoption("--use-real-paths"):
        return _REAL_PROJECT_ROOT_AT_CONFTEST_IMPORT
    return _apply_kb_path_patches(tmp_path, monkeypatch, mkdir=True)


# Cycle 17 AC16 — `_kb_sandbox` is an alias for `tmp_kb_env` kept for the
# design-gate naming convention. New code should prefer `tmp_kb_env` (cycle 12).
# Cycle 64 AC1: promoted to public `kb_sandbox` alias; `_kb_sandbox` kept for
# backward-compat with any test still referencing the private name.
kb_sandbox = tmp_kb_env
_kb_sandbox = tmp_kb_env


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

    Cycle 38 AC1 — DUAL-SITE patch (kb.utils.llm.call_llm_json BEFORE
    kb.capture.call_llm_json). Defends against contamination of
    sys.modules["kb.capture"] (cycle-19 L2 / cycle-20 L1 reload-leak class
    AND cycle-36 ubuntu-probe sys.modules deletion). Apply utils.llm FIRST
    so any subsequent re-import of kb.capture picks up the mocked function
    via ``from kb.utils.llm import call_llm_json``. Cycle 38 AC0 also
    refactored TestSymlinkGuard to subprocess so the in-process
    sys.modules deletion no longer happens at all; this dual-site patch
    is defense-in-depth for any future contamination introduced.

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

        # Cycle 38 AC1 — install order INVARIANT: utils.llm MUST be patched
        # BEFORE kb.capture. Rationale: any subsequent `del sys.modules["kb.capture"]`
        # + reimport (cycle-36 contamination class) re-executes kb.capture's
        # module-top `from kb.utils.llm import call_llm_json` which snapshots
        # whatever value is currently bound on kb.utils.llm. Patching utils.llm
        # FIRST guarantees the re-import picks up the mock; patching kb.capture
        # second covers the in-place call path that does NOT re-import. Reversing
        # the order is incorrect — see r1-sonnet-review §4 for the analysis.
        monkeypatch.setattr("kb.utils.llm.call_llm_json", fake_call)
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
