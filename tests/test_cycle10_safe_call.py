from kb.lint._safe_call import _safe_call
from kb.lint.runner import run_all_checks
from kb.mcp import health
from kb.mcp.health import kb_lint


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


def test_kb_lint_surfaces_sanitised_feedback_error_from_caller(tmp_project, tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError(f"disk read error at {tmp_path}/feedback.json")

    monkeypatch.setattr(health, "PROJECT_ROOT", tmp_project)
    monkeypatch.setattr("kb.feedback.reliability.get_flagged_pages", boom)

    response = kb_lint(wiki_dir=str(tmp_project / "wiki"))

    assert "feedback_flagged_pages_error:" in response
    assert str(tmp_path) not in response


def test_lint_runner_surfaces_sanitised_verdict_history_error(tmp_project, tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError(f"cannot read {tmp_path}/verdicts.json")

    monkeypatch.setattr("kb.lint.runner.get_verdict_summary", boom)

    report = run_all_checks(wiki_dir=tmp_project / "wiki", raw_dir=tmp_project / "raw")

    assert "verdict_history_error" in report
    assert str(tmp_path) not in report["verdict_history_error"]
