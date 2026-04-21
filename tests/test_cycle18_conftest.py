"""Cycle 18 AC1/AC2/AC3 — tmp_kb_env fixture redirects HASH_MANIFEST.

The manifest path lives at `kb.compile.compiler.HASH_MANIFEST`. Tests that use
`tmp_kb_env` should write manifest entries to `<tmp>/.data/hashes.json`, NOT
to the real `PROJECT_ROOT/.data/hashes.json`.
"""

from __future__ import annotations

from pathlib import Path


def test_hash_manifest_redirected_in_fixture(tmp_kb_env: Path) -> None:
    """AC1/AC2 — fixture patches kb.compile.compiler.HASH_MANIFEST to tmp path."""
    from kb.compile import compiler  # noqa: PLC0415

    expected = tmp_kb_env / ".data" / "hashes.json"
    assert compiler.HASH_MANIFEST == expected, (
        f"Expected HASH_MANIFEST to be {expected}, got {compiler.HASH_MANIFEST}"
    )


def test_hash_manifest_redirected_on_ingest(tmp_kb_env: Path) -> None:
    """AC3 — ingest_source under tmp_kb_env writes manifest to tmp, not prod.

    Sets up a small raw source, calls ingest_source with a stub extraction, and
    asserts:
      (i) `<tmp>/.data/hashes.json` exists with the ingested source_ref entry;
      (ii) the real `PROJECT_ROOT/.data/hashes.json` (captured pre-ingest) was
           not written to during the test (mtime unchanged or file absent).

    Note: `tests.*` modules that `from kb.compile.compiler import HASH_MANIFEST`
    at module top-level BEFORE tmp_kb_env runs are NOT covered by the mirror-
    rebind loop — grep-verified 2026-04-20 that no current test does this.
    """
    # Capture production manifest mtime before the test (if file exists).
    # The production PROJECT_ROOT has been patched to tmp_kb_env, so we cannot
    # read it from kb.config. Build a canonical absolute path relative to this
    # test file instead (tests/ lives at <repo>/tests, so repo root is parent).
    real_project_root = Path(__file__).resolve().parent.parent
    real_manifest = real_project_root / ".data" / "hashes.json"
    pre_mtime_ns = real_manifest.stat().st_mtime_ns if real_manifest.exists() else None

    # Seed a small raw article under the patched raw dir.
    raw_article = tmp_kb_env / "raw" / "articles" / "cycle18_fixture_test.md"
    raw_article.write_text(
        "# Cycle 18 Fixture Test\n\nSmall test source for HASH_MANIFEST redirection.\n",
        encoding="utf-8",
    )

    # Stub extraction — pre-built dict avoids any LLM call.
    stub_extraction = {
        "title": "Cycle 18 Fixture Test",
        "summary": "Small test source.",
        "entities_mentioned": [],
        "concepts_mentioned": [],
        "key_points": ["Fixture redirection check."],
    }

    from kb.ingest.pipeline import ingest_source  # noqa: PLC0415

    result = ingest_source(
        raw_article,
        source_type="article",
        extraction=stub_extraction,
        wiki_dir=tmp_kb_env / "wiki",
        raw_dir=tmp_kb_env / "raw",
    )
    assert result is not None
    assert "content_hash" in result

    # AC3(i): tmp manifest exists with entries.
    tmp_manifest = tmp_kb_env / ".data" / "hashes.json"
    assert tmp_manifest.exists(), (
        f"tmp_kb_env did not redirect HASH_MANIFEST write — tmp manifest missing at {tmp_manifest}"
    )
    import json  # noqa: PLC0415

    tmp_data = json.loads(tmp_manifest.read_text(encoding="utf-8"))
    # Some entry keyed on raw/articles/cycle18_fixture_test.md should exist
    assert any("cycle18_fixture_test" in key for key in tmp_data.keys()), (
        f"tmp manifest does not contain the ingested source: keys={list(tmp_data.keys())}"
    )

    # AC3(ii): production manifest mtime unchanged (or still absent).
    if pre_mtime_ns is None:
        assert not real_manifest.exists(), (
            f"Production manifest was CREATED during tmp_kb_env test: {real_manifest}"
        )
    else:
        post_mtime_ns = real_manifest.stat().st_mtime_ns
        assert post_mtime_ns == pre_mtime_ns, (
            f"Production manifest was WRITTEN during tmp_kb_env test: "
            f"pre={pre_mtime_ns} post={post_mtime_ns}"
        )


def test_patched_names_tuple_includes_hash_manifest() -> None:
    """AC1 — _TMP_KB_ENV_PATCHED_NAMES includes HASH_MANIFEST (tuple-membership check)."""
    from tests.conftest import _TMP_KB_ENV_PATCHED_NAMES  # noqa: PLC0415

    assert "HASH_MANIFEST" in _TMP_KB_ENV_PATCHED_NAMES, (
        "AC1: _TMP_KB_ENV_PATCHED_NAMES must include HASH_MANIFEST"
    )
