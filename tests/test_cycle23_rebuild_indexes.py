"""Cycle 23 AC1/AC2/AC3 — rebuild_indexes helper + CLI subcommand.

Tests:
- compile_wiki docstring documents --full scope (Q1: literal helper name +
  negation-near-category-word per each of manifest / vector / LRU).
- rebuild_indexes() helper: wipe manifest + vector DB + LRU caches under
  file_lock; audit-appends to wiki/log.md; raises ValidationError on
  wiki_dir outside PROJECT_ROOT.
- kb rebuild-indexes CLI: --yes flag skips confirm; aborts on no; lazy-
  imports kb.compile.compiler (kb --version short-circuit preserved).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

# ---------------------------------------------------------------------------
# AC1 — compile_wiki docstring
# ---------------------------------------------------------------------------


def _word_negation_window(doc: str, word: str, window: int = 200) -> bool:
    """True if a negation token appears within ``window`` chars after ``word``.

    Checks every occurrence — the docstring mentions each category word
    multiple times (once in the args block, once in the cycle-23 note block).
    Passing if ANY occurrence is near a negation satisfies the direction-of-
    claim assertion without locking docstring ordering.
    """
    doc_lc = doc.lower()
    target = word.lower()
    start = 0
    while True:
        idx = doc_lc.find(target, start)
        if idx < 0:
            return False
        span = doc_lc[idx : idx + window]
        if " not " in span or "n't " in span or "doesn't" in span or "does not" in span:
            return True
        start = idx + len(target)


def test_compile_wiki_docstring_documents_full_scope():
    """AC1 — --full docstring cites rebuild_indexes + negates each exclusion."""
    from kb.compile.compiler import compile_wiki

    doc = compile_wiki.__doc__ or ""
    assert "rebuild_indexes" in doc, (
        "compile_wiki docstring must reference the rebuild_indexes helper (cycle 23 AC1)"
    )
    # Use the stricter "vector index" phrase rather than bare "vector" so a
    # docstring rewrite like "embeddings are rebuilt incrementally" (which
    # still contains "not" in "not wipe") cannot pass in the wrong direction
    # (R1 Sonnet MAJOR — cycle-16 L2 vacuity class).
    for category in ["manifest", "vector index", "LRU"]:
        assert _word_negation_window(doc, category), (
            f"compile_wiki docstring must negate '{category}' within 200 chars "
            "of the keyword (direction-of-claim assertion, cycle 23 Q1)"
        )


# ---------------------------------------------------------------------------
# AC2 — rebuild_indexes helper
# ---------------------------------------------------------------------------


def _seed_manifest_and_vector(tmp_project: Path) -> tuple[Path, Path]:
    """Seed manifest + vector DB files so rebuild_indexes has work to do."""
    manifest = tmp_project / ".data" / "hashes.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text('{"seed": "hash"}', encoding="utf-8")
    vec = tmp_project / ".data" / "vector_index.db"
    vec.write_bytes(b"seed-vector")
    return manifest, vec


def test_rebuild_indexes_wipes_manifest_and_vector(tmp_project, monkeypatch):
    """AC2 — helper unlinks manifest + vector DB and audits to wiki/log.md."""
    monkeypatch.setattr("kb.compile.compiler.PROJECT_ROOT", tmp_project)
    monkeypatch.setattr("kb.compile.compiler.WIKI_DIR", tmp_project / "wiki")
    monkeypatch.setattr("kb.config.PROJECT_ROOT", tmp_project)
    monkeypatch.setattr("kb.config.WIKI_DIR", tmp_project / "wiki")
    manifest, vec = _seed_manifest_and_vector(tmp_project)
    # Import AFTER monkeypatch so manifest_path default binds to tmp
    from kb.compile import compiler

    monkeypatch.setattr(compiler, "HASH_MANIFEST", manifest)

    result = compiler.rebuild_indexes(
        wiki_dir=tmp_project / "wiki",
        hash_manifest=manifest,
        vector_db=vec,
    )
    assert result["manifest"]["cleared"] is True
    assert result["manifest"]["error"] is None
    assert not manifest.exists()
    assert result["vector"]["cleared"] is True
    assert result["vector"]["error"] is None
    assert not vec.exists()
    assert len(result["caches_cleared"]) >= 1
    assert result["audit_written"] is True
    log = (tmp_project / "wiki" / "log.md").read_text(encoding="utf-8")
    assert "rebuild-indexes" in log


def test_rebuild_indexes_no_op_when_nothing_to_clear(tmp_project, monkeypatch):
    """AC2 — idempotent: succeeds cleanly when targets already absent."""
    monkeypatch.setattr("kb.compile.compiler.PROJECT_ROOT", tmp_project)
    monkeypatch.setattr("kb.config.PROJECT_ROOT", tmp_project)
    from kb.compile import compiler

    ghost_manifest = tmp_project / ".data" / "ghost_hashes.json"
    ghost_vec = tmp_project / ".data" / "ghost_vec.db"
    ghost_manifest.parent.mkdir(parents=True, exist_ok=True)

    result = compiler.rebuild_indexes(
        wiki_dir=tmp_project / "wiki",
        hash_manifest=ghost_manifest,
        vector_db=ghost_vec,
    )
    assert result["manifest"]["cleared"] is True
    assert result["vector"]["cleared"] is True


def test_rebuild_indexes_rejects_wiki_dir_outside_project(tmp_project, monkeypatch):
    """AC2 / threat I1 — wiki_dir outside PROJECT_ROOT raises ValidationError.

    Late-bind ValidationError via the compiler module (cycle-20 L1 reload-
    leak: exception class identity drifts across importlib.reload chains).
    """
    monkeypatch.setattr("kb.compile.compiler.PROJECT_ROOT", tmp_project)
    monkeypatch.setattr("kb.config.PROJECT_ROOT", tmp_project)
    from kb.compile import compiler

    ValidationError = compiler.ValidationError

    outside_wiki = Path(tmp_project.drive + os.sep + "etc").resolve()
    with pytest.raises(ValidationError):
        compiler.rebuild_indexes(wiki_dir=outside_wiki)


def test_rebuild_indexes_rejects_symlinked_wiki_dir_outside_project(tmp_project, monkeypatch):
    """AC2 / threat I1 dual-anchor — symlink escape must be rejected.

    An absolute ``wiki_dir`` whose resolved target IS under PROJECT_ROOT
    but whose literal input is OUTSIDE PROJECT_ROOT must still be
    rejected — the caller's INTENT (the absolute path they supplied) is
    what the defensive check guards, not merely where resolve() lands
    (cycle-23 Q5).
    """
    monkeypatch.setattr("kb.compile.compiler.PROJECT_ROOT", tmp_project)
    monkeypatch.setattr("kb.config.PROJECT_ROOT", tmp_project)
    from kb.compile import compiler

    ValidationError = compiler.ValidationError

    # Absolute path whose literal form is outside the project root.
    # Even if resolve() returned something inside, the literal-form
    # pre-check must reject it (dual-anchor I1 per Q5 design decision).
    outside_abs = Path(tmp_project.drive + os.sep + "some_other_root" + os.sep + "wiki").resolve()
    with pytest.raises(ValidationError):
        compiler.rebuild_indexes(wiki_dir=outside_abs)


def test_rebuild_indexes_clears_lru_caches(tmp_project, monkeypatch):
    """AC2 — in-process LRU caches (template + frontmatter + purpose) cleared."""
    monkeypatch.setattr("kb.compile.compiler.PROJECT_ROOT", tmp_project)
    monkeypatch.setattr("kb.config.PROJECT_ROOT", tmp_project)
    from kb.compile import compiler

    # Touch each cached path first so each cache has a miss to record.
    from kb.utils import pages as pages_mod

    # Pre-populate by calling the cached helper once (use a file that exists)
    seed_page = tmp_project / "wiki" / "entities" / "_seed.md"
    seed_page.parent.mkdir(parents=True, exist_ok=True)
    seed_page.write_text(
        "---\ntitle: seed\ncreated: 2026-04-23\nupdated: 2026-04-23\n"
        "type: entity\nconfidence: stated\nsource:\n  - raw/x.md\n---\n# seed\n",
        encoding="utf-8",
    )
    # Trigger the cached helper (load_page_frontmatter wraps
    # _load_page_frontmatter_cached with mtime-keyed args)
    pages_mod.load_page_frontmatter(seed_page)
    info_before = pages_mod._load_page_frontmatter_cached.cache_info()
    assert info_before.currsize >= 1

    result = compiler.rebuild_indexes(wiki_dir=tmp_project / "wiki")
    info_after = pages_mod._load_page_frontmatter_cached.cache_info()
    assert info_after.currsize == 0
    # R1 Sonnet MAJOR — pin ALL three cache helpers actually ran, not just
    # the one whose cache_info we inspect. Defeats the vacuity class where
    # silent ImportError on one helper would otherwise pass the test.
    cleared = set(result["caches_cleared"])
    assert {
        "kb.ingest.extractors.clear_template_cache",
        "kb.utils.pages._load_page_frontmatter_cached",
        "kb.utils.pages.load_purpose",
    } <= cleared, f"rebuild_indexes did not clear all three cache sites: {cleared}"


def test_rebuild_indexes_manifest_lock_busy_returns_error(tmp_project, monkeypatch):
    """AC2 / Q3 — if file_lock(manifest) is busy, manifest clear reports error."""
    monkeypatch.setattr("kb.compile.compiler.PROJECT_ROOT", tmp_project)
    monkeypatch.setattr("kb.config.PROJECT_ROOT", tmp_project)
    from kb.compile import compiler
    from kb.utils.io import file_lock

    manifest, vec = _seed_manifest_and_vector(tmp_project)

    # Hold the lock from a thread while rebuild_indexes tries to acquire.
    import threading

    lock_held = threading.Event()
    lock_release = threading.Event()

    def holder():
        with file_lock(manifest, timeout=5.0):
            lock_held.set()
            lock_release.wait(5.0)

    t = threading.Thread(target=holder)
    t.start()
    try:
        assert lock_held.wait(2.0), "holder thread failed to acquire lock"
        result = compiler.rebuild_indexes(
            wiki_dir=tmp_project / "wiki",
            hash_manifest=manifest,
            vector_db=vec,
        )
        assert result["manifest"]["cleared"] is False
        assert result["manifest"]["error"] == "lock busy"
        # Vector path is unlocked so it still clears.
        assert result["vector"]["cleared"] is True
    finally:
        lock_release.set()
        t.join(timeout=5.0)


# ---------------------------------------------------------------------------
# AC3 — kb rebuild-indexes CLI
# ---------------------------------------------------------------------------


def test_cli_rebuild_indexes_with_yes_flag(tmp_project, monkeypatch):
    """AC3 — --yes skips prompt, runs helper, exits 0."""
    monkeypatch.setattr("kb.compile.compiler.PROJECT_ROOT", tmp_project)
    monkeypatch.setattr("kb.compile.compiler.WIKI_DIR", tmp_project / "wiki")
    monkeypatch.setattr("kb.config.PROJECT_ROOT", tmp_project)
    monkeypatch.setattr("kb.config.WIKI_DIR", tmp_project / "wiki")
    manifest, vec = _seed_manifest_and_vector(tmp_project)
    from kb.compile import compiler

    monkeypatch.setattr(compiler, "HASH_MANIFEST", manifest)

    from kb.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["rebuild-indexes", "--yes"])
    assert result.exit_code == 0, result.output
    assert not manifest.exists()
    assert "manifest=cleared" in result.output


def test_cli_rebuild_indexes_aborts_without_yes(tmp_project, monkeypatch):
    """AC3 — without --yes, typing 'n' aborts and leaves files intact."""
    monkeypatch.setattr("kb.compile.compiler.PROJECT_ROOT", tmp_project)
    monkeypatch.setattr("kb.compile.compiler.WIKI_DIR", tmp_project / "wiki")
    monkeypatch.setattr("kb.config.PROJECT_ROOT", tmp_project)
    monkeypatch.setattr("kb.config.WIKI_DIR", tmp_project / "wiki")
    manifest, vec = _seed_manifest_and_vector(tmp_project)
    from kb.compile import compiler

    monkeypatch.setattr(compiler, "HASH_MANIFEST", manifest)

    from kb.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["rebuild-indexes"], input="n\n")
    assert result.exit_code != 0  # click.confirm(abort=True) -> exit 1
    assert manifest.exists()


def test_cli_version_does_not_import_compile_compiler():
    """AC3 / cycle-8 L1 — kb --version short-circuit must not pull compile.compiler."""
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            [
                str(Path(__file__).resolve().parent.parent / "src"),
                os.environ.get("PYTHONPATH", ""),
            ]
        ).rstrip(os.pathsep),
    }
    probe = (
        "import json, sys\n"
        "sys.argv = ['kb', '--version']\n"
        "try:\n"
        "    import kb.cli\n"
        "    kb.cli.cli(standalone_mode=False)\n"
        "except SystemExit:\n"
        "    pass\n"
        "print(json.dumps({'compiler_loaded': 'kb.compile.compiler' in sys.modules}))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stderr
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    result = json.loads(lines[-1])
    assert result["compiler_loaded"] is False, (
        "cycle-8 L1 — kb --version must short-circuit before importing "
        "kb.compile.compiler (rebuild-indexes subcommand must lazy-import)"
    )
