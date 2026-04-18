from kb.lint._safe_call import _safe_call


def test_safe_call_sanitises_absolute_path_in_exception_message(monkeypatch):
    def boom():
        raise OSError("disk full at /home/user/secret/path/feedback.json")

    monkeypatch.setattr(boom, "__name__", "boom")

    result, err = _safe_call(boom, fallback=[], label="verdict_history")

    assert result == []
    assert err is not None
    assert "disk full" in err
    assert "verdict_history_error:" in err
    assert "/home/user/secret/path/feedback.json" not in err


def test_safe_call_preserves_message_when_no_path_leaks(monkeypatch):
    def boom():
        raise ValueError("bad input value")

    monkeypatch.setattr(boom, "__name__", "boom")

    result, err = _safe_call(boom, fallback=[], label="feedback")

    assert result == []
    assert err == "feedback_error: ValueError: bad input value"
