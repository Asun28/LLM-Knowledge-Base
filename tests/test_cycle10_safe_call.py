from kb.lint._safe_call import _safe_call


def test_safe_call_sanitises_absolute_path_in_exception_message(tmp_path, monkeypatch):
    secret_path = str(tmp_path / "secret.json")

    def boom():
        raise OSError(f"disk full at {secret_path}")

    monkeypatch.setattr(boom, "__name__", "boom")

    result, err = _safe_call(boom, fallback=[], label="verdict_history")

    assert result == []
    assert err is not None
    assert "disk full" in err
    assert "verdict_history_error:" in err
    assert str(tmp_path) not in err


def test_safe_call_sanitises_absolute_path_in_feedback_exception_message(tmp_path, monkeypatch):
    secret_path = str(tmp_path / "secret.json")

    def boom():
        raise OSError(f"disk full at {secret_path}")

    monkeypatch.setattr(boom, "__name__", "boom")

    result, err = _safe_call(boom, fallback=[], label="feedback")

    assert result == []
    assert err is not None
    assert "disk full" in err
    assert "feedback_error:" in err
    assert str(tmp_path) not in err
