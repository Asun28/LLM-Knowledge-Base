"""Regression tests for kb.utils.io — file_lock SIGINT safety + sweep_orphan_tmp behaviors."""

import os
import time

from kb.utils import io as io_mod
from kb.utils.io import atomic_json_write, atomic_text_write, file_lock, sweep_orphan_tmp


def test_file_lock_cleans_up_on_exception_during_acquire(tmp_path, monkeypatch):
    """Regression: Phase 4.5 CRITICAL item 15.

    SIGINT between os.write and try: left orphan lock.
    """
    target = tmp_path / "data.json"
    target.write_text("{}", encoding="utf-8")
    orig_close = io_mod.os.close
    closed = {"called": False}

    def evil_close(fd):
        if not closed["called"]:
            closed["called"] = True
            orig_close(fd)
            raise KeyboardInterrupt("simulated SIGINT")
        orig_close(fd)

    monkeypatch.setattr(io_mod.os, "close", evil_close)
    try:
        with io_mod.file_lock(target):
            pass
    except KeyboardInterrupt:
        pass
    lock_path = target.with_suffix(target.suffix + ".lock")
    assert not lock_path.exists(), f"orphan lock survived SIGINT: {lock_path}"


# ── Cycle 12 — sweep_orphan_tmp + io doc caveats (folded from test_cycle12_io_sweep.py) ─


def test_sweep_orphan_tmp_removes_only_old_top_level_tmp(tmp_path):
    old_tmp = tmp_path / "old.tmp"
    fresh_tmp = tmp_path / "fresh.tmp"
    nested_dir = tmp_path / "nested"
    nested_dir.mkdir()
    nested_tmp = nested_dir / "old-nested.tmp"

    old_tmp.write_text("old", encoding="utf-8")
    fresh_tmp.write_text("fresh", encoding="utf-8")
    nested_tmp.write_text("nested", encoding="utf-8")

    now = time.time()
    os.utime(old_tmp, (now - 7200, now - 7200))
    os.utime(fresh_tmp, (now, now))
    os.utime(nested_tmp, (now - 7200, now - 7200))

    assert sweep_orphan_tmp(tmp_path) == 1

    assert not old_tmp.exists()
    assert fresh_tmp.exists()
    assert nested_tmp.exists()


def test_sweep_orphan_tmp_is_non_recursive(tmp_path):
    nested_dir = tmp_path / "nested"
    nested_dir.mkdir()
    nested_tmp = nested_dir / "old.tmp"
    nested_tmp.write_text("nested", encoding="utf-8")

    now = time.time()
    os.utime(nested_tmp, (now - 7200, now - 7200))

    assert sweep_orphan_tmp(tmp_path) == 0
    assert nested_tmp.exists()


def test_sweep_orphan_tmp_logs_warning_and_continues_on_unlink_error(
    tmp_path,
    monkeypatch,
    caplog,
):
    old_tmp = tmp_path / "old.tmp"
    old_tmp.write_text("old", encoding="utf-8")
    now = time.time()
    os.utime(old_tmp, (now - 7200, now - 7200))

    def fail_unlink(self, *args, **kwargs):
        raise OSError("simulated unlink failure")

    monkeypatch.setattr(io_mod.Path, "unlink", fail_unlink)

    with caplog.at_level("WARNING", logger=io_mod.logger.name):
        assert sweep_orphan_tmp(tmp_path) == 0

    assert old_tmp.exists()
    assert str(old_tmp.resolve()) in caplog.text
    assert "simulated unlink failure" in caplog.text


def test_sweep_orphan_tmp_never_raises_on_missing_directory(tmp_path, caplog):
    """AC2 security-verify fix: caller-supplied directory may not exist; helper
    must log WARNING and return 0 — never raise past the boundary. Exists so
    CLI boot / ingest-tail callers can invoke unconditionally.
    """
    missing = tmp_path / "does-not-exist"
    with caplog.at_level("WARNING", logger=io_mod.logger.name):
        assert sweep_orphan_tmp(missing) == 0
    assert "does not exist" in caplog.text or "not a directory" in caplog.text


def test_sweep_orphan_tmp_never_raises_on_non_directory(tmp_path, caplog):
    """AC2 security-verify fix: a path that exists but is a regular file must
    log WARNING and return 0, not raise NotADirectoryError during glob.
    """
    file_path = tmp_path / "regular.txt"
    file_path.write_text("i am a file", encoding="utf-8")
    with caplog.at_level("WARNING", logger=io_mod.logger.name):
        assert sweep_orphan_tmp(file_path) == 0
    assert "not a directory" in caplog.text


def test_load_page_frontmatter_docstring_documents_mtime_caveat():
    """Cycle 43 AC9 — vacuous-test fold per C40-L3 (do not auto-upgrade).

    AC8 security-verify fix: design-gate condition 3 requires the helper to
    document the coarse-filesystem mtime resolution caveat so future
    maintainers understand the cache-key collision window on FAT32/SMB. This
    is a docstring-introspection assertion; reverting any actual cache logic
    in `load_page_frontmatter` would NOT fail it. See BACKLOG.md Phase 4.5
    HIGH #4 vacuous-test upgrade candidate entry for the behavior-based
    replacement plan.
    """
    from kb.utils.pages import load_page_frontmatter

    doc = load_page_frontmatter.__doc__ or ""
    assert "mtime" in doc.lower()
    assert "filesystem" in doc.lower()
    # Mention at least one coarse-resolution filesystem explicitly
    assert any(name in doc for name in ("FAT32", "SMB", "OneDrive"))


def test_cycle12_io_doc_caveats_are_present():
    """Cycle 43 AC9 — vacuous-test fold per C40-L3 (do not auto-upgrade).

    Asserts file_lock / atomic_json_write / atomic_text_write docstrings
    contain specific caveat strings (PID recycling, OneDrive, sweep_orphan_tmp).
    Reverting any actual lock-recycling or atomic-write logic would NOT fail
    this. See BACKLOG.md Phase 4.5 HIGH #4 vacuous-test upgrade candidate
    entry for the behavior-based replacement plan.
    """
    assert file_lock.__doc__ is not None
    assert "PID" in file_lock.__doc__
    assert "recycling" in file_lock.__doc__

    assert atomic_json_write.__doc__ is not None
    assert "OneDrive" in atomic_json_write.__doc__
    assert "sweep_orphan_tmp" in atomic_json_write.__doc__

    assert atomic_text_write.__doc__ is not None
    assert "OneDrive" in atomic_text_write.__doc__
    assert "sweep_orphan_tmp" in atomic_text_write.__doc__
