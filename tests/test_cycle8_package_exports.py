"""Cycle 8 package export coverage."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"


def _run_import_probe(code: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SRC_DIR) if not existing else f"{SRC_DIR}{os.pathsep}{existing}"
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_kb_top_level_exports_importable_in_fresh_subprocess():
    result = _run_import_probe(
        "from kb import ("
        "ingest_source, compile_wiki, query_wiki, build_graph, "
        "WikiPage, RawSource, LLMError, __version__"
        ")"
    )

    assert result.returncode == 0, result.stderr


def test_kb_top_level_all_is_curated():
    import kb

    # Cycle 20 AC3 — kb.errors taxonomy exports added: KBError + 5 subclasses.
    assert kb.__all__ == [
        "ingest_source",
        "compile_wiki",
        "query_wiki",
        "build_graph",
        "WikiPage",
        "RawSource",
        "LLMError",
        "KBError",
        "IngestError",
        "CompileError",
        "QueryError",
        "ValidationError",
        "StorageError",
        "__version__",
    ]


def test_utils_exports_importable_in_fresh_subprocess():
    result = _run_import_probe(
        "from kb.utils import ("
        "slugify, yaml_escape, yaml_sanitize, STOPWORDS, atomic_json_write, "
        "atomic_text_write, file_lock, content_hash, extract_wikilinks, "
        "extract_raw_refs, FRONTMATTER_RE, append_wiki_log, load_all_pages, "
        "normalize_sources, make_source_ref"
        ")"
    )

    assert result.returncode == 0, result.stderr


def test_utils_all_is_curated():
    import kb.utils as utils

    assert utils.__all__ == [
        "slugify",
        "yaml_escape",
        "yaml_sanitize",
        "STOPWORDS",
        "atomic_json_write",
        "atomic_text_write",
        "file_lock",
        "content_hash",
        "extract_wikilinks",
        "extract_raw_refs",
        "FRONTMATTER_RE",
        "append_wiki_log",
        "load_all_pages",
        "normalize_sources",
        "make_source_ref",
    ]


def test_models_exports_importable_in_fresh_subprocess():
    result = _run_import_probe("from kb.models import WikiPage, RawSource")

    assert result.returncode == 0, result.stderr


def test_models_all_is_curated():
    import kb.models as models

    assert models.__all__ == ["WikiPage", "RawSource"]
