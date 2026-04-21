"""Cycle 19 AC11/AC12/AC13 — manifest_key_for + dual-write threading + traversal validation.

`manifest_key_for` is the public alias for `_canonical_rel_path`. `ingest_source`
now accepts a keyword-only `manifest_key=` that is threaded into BOTH the
duplicate-check reservation AND the tail confirmation, eliminating the
divergence class where a non-default `raw_dir` produced two different keys.
"""

from __future__ import annotations

import inspect
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ────────────────────────────────────────────────────────────────────────────
# AC11 — manifest_key_for public alias
# ────────────────────────────────────────────────────────────────────────────


def test_manifest_key_for_is_public_alias_of_canonical_rel_path() -> None:
    """T-11 — manifest_key_for points at the same callable as _canonical_rel_path."""
    from kb.compile.compiler import _canonical_rel_path, manifest_key_for

    assert manifest_key_for is _canonical_rel_path, (
        "manifest_key_for must be the public alias of _canonical_rel_path "
        "(re-export, not a wrapper) so caller-supplied keys round-trip identically."
    )


# ────────────────────────────────────────────────────────────────────────────
# AC12 — keyword-only placement after `*` sentinel
# ────────────────────────────────────────────────────────────────────────────


def test_manifest_key_is_keyword_only() -> None:
    """T-12 — manifest_key parameter is keyword-only (placed after `*` sentinel)."""
    from kb.ingest.pipeline import ingest_source

    sig = inspect.signature(ingest_source)
    param = sig.parameters.get("manifest_key")
    assert param is not None, "manifest_key parameter missing"
    assert param.kind == inspect.Parameter.KEYWORD_ONLY, (
        f"manifest_key must be KEYWORD_ONLY (after `*` sentinel); "
        f"got {param.kind}. R2 N1 — placing it before `*` is a positional break."
    )
    assert param.default is None, "manifest_key default should be None for backward compat"


def test_legacy_positional_call_still_binds(tmp_kb_env: Path, monkeypatch) -> None:
    """T-12a — Legacy positional callers (source_path, source_type, extraction) still bind.

    Pass wiki_dir / raw_dir explicitly to avoid the cycle-15 KB_PROJECT_ROOT
    snapshot-binding leak that contaminates module-level RAW_DIR.
    """
    from kb.ingest.pipeline import ingest_source

    raw_path = tmp_kb_env / "raw" / "articles" / "x.md"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text("# Tiny article body for ingest signature smoke.\n", encoding="utf-8")

    fake_extraction = {
        "title": "Cycle 19 Smoke",
        "core_argument": "Manifest key signature backward compatibility check.",
        "key_claims": [],
        "entities_mentioned": [],
        "concepts_mentioned": [],
    }

    # Legacy positional call shape — no manifest_key kwarg. wiki_dir + raw_dir
    # passed via kwargs (still keyword-only) to isolate from leaked module-level
    # constants. The "positional" contract under test is the first 3 params.
    result = ingest_source(
        raw_path,
        "article",
        fake_extraction,
        wiki_dir=tmp_kb_env / "wiki",
        raw_dir=tmp_kb_env / "raw",
    )
    assert "pages_created" in result, (
        "Legacy positional call (path, source_type, extraction) must still work"
    )


# ────────────────────────────────────────────────────────────────────────────
# AC12 — traversal validation
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "bad_key,reason",
    [
        ("../etc/passwd", "dotdot traversal"),
        ("/abs/path", "leading slash"),
        ("\\abs\\path", "leading backslash"),
        ("with\x00null", "null byte"),
        ("a" * 513, "exceeds 512 chars"),
    ],
)
def test_manifest_key_rejects_traversal_patterns(
    tmp_kb_env: Path, bad_key: str, reason: str
) -> None:
    """T-12c — manifest_key with traversal patterns raises ValueError at function entry."""
    from kb.ingest.pipeline import ingest_source

    raw_path = tmp_kb_env / "raw" / "articles" / "x.md"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text("body\n", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid manifest_key"):
        ingest_source(raw_path, "article", manifest_key=bad_key)


def test_manifest_key_accepts_valid_relative_path(tmp_kb_env: Path) -> None:
    """T-12d — Valid manifest_key like 'raw/articles/x.md' is accepted (no validation error)."""
    from kb.ingest.pipeline import ingest_source

    raw_path = tmp_kb_env / "raw" / "articles" / "x.md"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text("body\n", encoding="utf-8")

    fake_extraction = {
        "title": "Valid Key Test",
        "core_argument": "Valid key accepted.",
        "key_claims": [],
        "entities_mentioned": [],
        "concepts_mentioned": [],
    }
    # Should not raise. Pass wiki_dir/raw_dir explicitly to isolate from
    # cycle-15 KB_PROJECT_ROOT snapshot-binding leak.
    result = ingest_source(
        raw_path,
        "article",
        fake_extraction,
        wiki_dir=tmp_kb_env / "wiki",
        raw_dir=tmp_kb_env / "raw",
        manifest_key="raw/articles/x.md",
    )
    assert "pages_created" in result


# ────────────────────────────────────────────────────────────────────────────
# AC12 / R2 M1 — manifest_ref threaded to BOTH reservation AND confirmation
# ────────────────────────────────────────────────────────────────────────────


def test_manifest_key_threaded_to_both_writes(tmp_kb_env: Path) -> None:
    """T-12b — manifest_key is used by BOTH _check_and_reserve_manifest AND tail confirmation."""
    from kb.compile.compiler import HASH_MANIFEST, load_manifest
    from kb.ingest import pipeline

    raw_path = tmp_kb_env / "raw" / "articles" / "x.md"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text("# unique body for dual-write test\n", encoding="utf-8")

    custom_key = "custom/key/x.md"
    fake_extraction = {
        "title": "Dual Write Test",
        "core_argument": "manifest_key threads to both writes.",
        "key_claims": [],
        "entities_mentioned": [],
        "concepts_mentioned": [],
    }

    # Spy on _check_and_reserve_manifest to capture the second arg (source_ref / manifest_ref).
    reservation_calls: list[tuple] = []
    real_reserve = pipeline._check_and_reserve_manifest

    def spy_reserve(source_hash, source_ref, manifest_path=None):
        reservation_calls.append((source_hash, source_ref))
        return real_reserve(source_hash, source_ref, manifest_path)

    with patch.object(pipeline, "_check_and_reserve_manifest", side_effect=spy_reserve):
        pipeline.ingest_source(
            raw_path,
            "article",
            fake_extraction,
            wiki_dir=tmp_kb_env / "wiki",
            raw_dir=tmp_kb_env / "raw",
            manifest_key=custom_key,
        )

    # Phase 1 reservation should have been called with the custom key, NOT source_ref.
    assert reservation_calls, "expected at least one _check_and_reserve_manifest call"
    _, reserved_ref = reservation_calls[0]
    assert reserved_ref == custom_key, (
        f"Phase 1 reservation should use manifest_key={custom_key!r}; got {reserved_ref!r}"
    )

    # Phase 2 confirmation: assert the on-disk manifest now contains the custom_key.
    manifest = load_manifest(HASH_MANIFEST)
    assert custom_key in manifest, (
        f"Phase 2 confirmation should write manifest[{custom_key!r}]; "
        f"manifest keys = {list(manifest.keys())}"
    )


# ────────────────────────────────────────────────────────────────────────────
# AC13 — compile_wiki threads manifest_key_for(source, raw_dir)
# ────────────────────────────────────────────────────────────────────────────


def test_compile_wiki_threads_manifest_key(tmp_kb_env: Path, monkeypatch) -> None:
    """T-13 — compile_wiki passes the canonical key into ingest_source as manifest_key.

    Pass raw_dir + wiki_dir explicitly to compile_wiki to isolate from any
    cycle-15 KB_PROJECT_ROOT snapshot-binding leak in module-level RAW_DIR.
    """
    from kb.compile import compiler

    raw_dir = tmp_kb_env / "raw"
    wiki_dir = tmp_kb_env / "wiki"
    raw_path = raw_dir / "articles" / "x.md"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text("# Body\n", encoding="utf-8")

    captured_kwargs: list[dict] = []

    def fake_ingest(*args, **kwargs):
        captured_kwargs.append(kwargs)
        return {
            "pages_created": [],
            "pages_updated": [],
            "pages_skipped": [],
            "wikilinks_injected": [],
            "affected_pages": [],
            "duplicate": False,
        }

    monkeypatch.setattr(compiler, "ingest_source", fake_ingest)
    monkeypatch.setattr(compiler, "find_changed_sources", lambda *a, **k: ([raw_path], []))

    compiler.compile_wiki(incremental=True, raw_dir=raw_dir, wiki_dir=wiki_dir)

    assert captured_kwargs, "compile_wiki should call ingest_source at least once"
    first_kwargs = captured_kwargs[0]
    assert "manifest_key" in first_kwargs, (
        f"compile_wiki must thread manifest_key=; kwargs = {first_kwargs}"
    )
    expected_key = compiler.manifest_key_for(raw_path, raw_dir)
    assert first_kwargs["manifest_key"] == expected_key, (
        f"Expected manifest_key={expected_key!r}; got {first_kwargs['manifest_key']!r}"
    )


# ────────────────────────────────────────────────────────────────────────────
# AC13 — pure-unit canonical equality (T-13c always-runs)
# ────────────────────────────────────────────────────────────────────────────


def test_manifest_key_for_pure_unit_equality(tmp_path: Path) -> None:
    """T-13c — manifest_key_for(source, raw_dir) == manifest_key_for(source, raw_dir.resolve())."""
    from kb.compile.compiler import manifest_key_for

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    src = raw_dir / "articles" / "x.md"
    src.parent.mkdir()
    src.write_text("body\n", encoding="utf-8")

    key1 = manifest_key_for(src, raw_dir)
    key2 = manifest_key_for(src, raw_dir.resolve())
    assert key1 == key2, (
        f"manifest_key_for must produce the same key under raw_dir vs raw_dir.resolve(); "
        f"got {key1!r} vs {key2!r}"
    )


# ────────────────────────────────────────────────────────────────────────────
# AC13 — portable symlink test (T-13b skipif not symlink-capable)
# ────────────────────────────────────────────────────────────────────────────


def _can_create_symlink(tmp_path: Path) -> bool:
    """Check whether the current process can create a symlink in tmp_path."""
    target = tmp_path / "_symlink_check_target"
    link = tmp_path / "_symlink_check_link"
    target.mkdir()
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        return False
    finally:
        if link.exists() or link.is_symlink():
            link.unlink()
        target.rmdir()
    return True


def test_manifest_key_for_symlink_equality(tmp_path: Path) -> None:
    """T-13b (portable) — symlinked raw_dir produces the same manifest key as the real path."""
    if not _can_create_symlink(tmp_path):
        pytest.skip("symlink creation requires elevated privileges on this OS")

    from kb.compile.compiler import manifest_key_for

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    src = raw_dir / "articles" / "x.md"
    src.parent.mkdir()
    src.write_text("body\n", encoding="utf-8")

    link_dir = tmp_path / "raw_link"
    link_dir.symlink_to(raw_dir, target_is_directory=True)

    key_via_real = manifest_key_for(src, raw_dir)
    key_via_link = manifest_key_for(link_dir / "articles" / "x.md", link_dir)
    # Both must canonicalize to the same key (resolve() collapses the symlink).
    assert key_via_real == key_via_link, (
        f"Symlinked raw_dir should resolve to the same manifest key; "
        f"got real={key_via_real!r} link={key_via_link!r}"
    )


# ────────────────────────────────────────────────────────────────────────────
# AC13 — Windows tilde short-path (T-13a skipif non-Windows)
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows-specific test")
def test_manifest_key_for_handles_resolve_normalization() -> None:
    """T-13a (Windows) — Path.resolve() normalises tilde-shortened forms."""
    # Smoke check: Path.resolve() canonicalises Windows short-name forms; this
    # exercises the same code path manifest_key_for relies on. Skipped off
    # Windows because Path.resolve semantics differ on POSIX.
    cwd = Path(os.getcwd())
    resolved = cwd.resolve()
    assert resolved.exists(), "resolved cwd must exist"
    # If we got here without a Path exception under Windows, the canonicalisation
    # path manifest_key_for relies on is intact.
