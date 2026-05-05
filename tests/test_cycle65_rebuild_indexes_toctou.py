"""AC10 — O_NOFOLLOW TOCTOU mitigation tests."""

import os
import sys
from pathlib import Path

import pytest

from kb.utils.path_safety import _open_no_follow


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlink test")
def test_symlink_swap_rejected_primary(tmp_path: Path) -> None:
    """C9 primary path — symlink should be rejected via O_NOFOLLOW."""
    # Create a real file
    real_file = tmp_path / "real.txt"
    real_file.write_text("test content")
    
    # Successfully open the real file
    fd = _open_no_follow(real_file)
    assert fd > 0, "Should successfully open a real file"
    os.close(fd)
    
    # Now create a symlink and verify it's rejected
    symlink_path = tmp_path / "link.txt"
    symlink_path.symlink_to(real_file)
    
    # Attempt to open the symlink should raise OSError
    with pytest.raises(OSError):
        _open_no_follow(symlink_path)


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Q2.3 fallback path is POSIX-only; Windows uses non-atomic is_symlink "
    "check directly (no warning emitted) per Step 12 fix.",
)
def test_symlink_swap_rejected_fallback(monkeypatch, tmp_path: Path, caplog) -> None:
    """Q2.3 fallback — when O_NOFOLLOW unavailable on POSIX, re-resolve and warn once."""
    real_file = tmp_path / "real.txt"
    real_file.write_text("test content")

    monkeypatch.setattr(
        "os.open",
        lambda *a, **k: (_ for _ in ()).throw(OSError("simulated failure")),
    )

    _open_no_follow(real_file)

    assert any("AC10" in record.message for record in caplog.records), (
        "Should log AC10 fallback warning"
    )


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Fallback warning only fires on POSIX path; Windows direct is_symlink check "
    "has no fallback to warn about.",
)
def test_warning_fires_only_once(monkeypatch, tmp_path: Path, caplog) -> None:
    """Fallback warning should fire once per process, not per call (POSIX only)."""
    real_file = tmp_path / "real.txt"
    real_file.write_text("test")

    monkeypatch.setattr(
        "os.open",
        lambda *a, **k: (_ for _ in ()).throw(OSError("simulated")),
    )

    import kb.utils.path_safety

    kb.utils.path_safety._warned_fallback = False

    caplog.clear()
    _open_no_follow(real_file)
    first_warnings = [r for r in caplog.records if "AC10" in r.message]
    assert len(first_warnings) == 1, "First call should produce one warning"

    caplog.clear()
    _open_no_follow(real_file)
    second_warnings = [r for r in caplog.records if "AC10" in r.message]
    assert len(second_warnings) == 0, "Second call should not warn (flag already set)"


def test_rebuild_indexes_invokes_open_no_follow_on_mutators(
    monkeypatch, tmp_kb_env, tmp_path: Path
) -> None:
    """AC10 integration — rebuild_indexes must route every unlink through
    _open_no_follow so a symlink cannot be swapped in between exists() and unlink().

    This is the production-path test that complements the helper-direct tests
    above. Without it AC10's helper would be defined-but-unused and the
    advertised TOCTOU mitigation would be vacuous (cycle-7-L1 inspect-source
    risk in disguise — function exists, not called from production).
    """
    import kb.compile.compiler as compiler_mod

    # Spy on _open_no_follow so we can assert calls + return a real-ish fd.
    open_calls: list[Path] = []
    close_calls: list[int] = []

    def fake_open(p: Path) -> int:
        open_calls.append(Path(p))
        return 7  # arbitrary non-(-1) sentinel

    def fake_close(fd: int) -> None:
        close_calls.append(fd)

    monkeypatch.setattr(compiler_mod, "_open_no_follow", fake_open)
    monkeypatch.setattr(compiler_mod, "_close_no_follow_fd", fake_close)

    # tmp_kb_env returns the project_root Path (with WIKI_/RAW_ tree mkdir'd).
    project_root = tmp_kb_env
    # AC10's _assert_under_project_root reads kb.config.get_project_root() which
    # bypasses the autouse fixture's module-level patch (the dead-branch issue
    # in the AC1 PEP 562 shim — see Step 10 simplify report). Set the env var
    # explicitly so containment passes for tmp_kb_env paths.
    monkeypatch.setenv("KB_PROJECT_ROOT", str(project_root))
    wiki_dir = project_root / "wiki"
    manifest = project_root / "hash_manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    vec_db = project_root / "vector_index.db"
    vec_db.write_bytes(b"")
    vec_tmp = project_root / "vector_index.db.tmp"
    vec_tmp.write_bytes(b"")

    # Ensure rebuild_indexes sees these paths (override is supported).
    result = compiler_mod.rebuild_indexes(
        wiki_dir=wiki_dir,
        hash_manifest=manifest,
        vector_db=vec_db,
    )

    # All three mutator paths should have routed through _open_no_follow.
    open_paths = {str(p) for p in open_calls}
    assert str(manifest) in open_paths, (
        f"manifest unlink bypassed _open_no_follow; spy saw {open_paths}"
    )
    assert str(vec_db) in open_paths, (
        f"vector_db unlink bypassed _open_no_follow; spy saw {open_paths}"
    )
    assert str(vec_tmp) in open_paths, (
        f"tmp sibling unlink bypassed _open_no_follow; spy saw {open_paths}"
    )

    # Each open() must be paired with a close(); spy returned fd=7 each time.
    assert close_calls.count(7) == len(open_calls), (
        f"close calls ({len(close_calls)}) do not match open calls ({len(open_calls)})"
    )

    # Production result should still report success (unlinks happened).
    assert result["manifest"]["cleared"] is True
    assert result["vector"]["cleared"] is True
