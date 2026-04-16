"""Regression tests for kb.utils.io — file_lock SIGINT safety."""


def test_file_lock_cleans_up_on_exception_during_acquire(tmp_path, monkeypatch):
    """Regression: Phase 4.5 CRITICAL item 15.

    SIGINT between os.write and try: left orphan lock.
    """
    from kb.utils import io as io_mod

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
