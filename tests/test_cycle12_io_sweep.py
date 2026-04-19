"""Cycle 12 coverage for orphan atomic-write temp cleanup."""

import os
import time

from kb.utils import io as io_mod
from kb.utils.io import atomic_json_write, atomic_text_write, file_lock, sweep_orphan_tmp


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


def test_cycle12_io_doc_caveats_are_present():
    assert file_lock.__doc__ is not None
    assert "PID" in file_lock.__doc__
    assert "recycling" in file_lock.__doc__

    assert atomic_json_write.__doc__ is not None
    assert "OneDrive" in atomic_json_write.__doc__
    assert "sweep_orphan_tmp" in atomic_json_write.__doc__

    assert atomic_text_write.__doc__ is not None
    assert "OneDrive" in atomic_text_write.__doc__
    assert "sweep_orphan_tmp" in atomic_text_write.__doc__
