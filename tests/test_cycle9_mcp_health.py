"""Cycle 9 health MCP feedback path isolation regressions."""

import json
from pathlib import Path


def _write_feedback(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _feedback_with_low_trust_page(page_id: str) -> dict:
    return {
        "entries": [],
        "page_scores": {
            page_id: {
                "useful": 0,
                "wrong": 2,
                "incomplete": 0,
                "trust": 0.1667,
            }
        },
    }


def _feedback_with_coverage_gap(question: str) -> dict:
    return {
        "entries": [
            {
                "timestamp": "2026-04-18T00:00:00",
                "question": question,
                "rating": "incomplete",
                "cited_pages": [],
                "notes": "production-only coverage gap",
            }
        ],
        "page_scores": {},
    }


def _install_lint_report(monkeypatch) -> None:
    import kb.lint.runner as runner

    monkeypatch.setattr(runner, "run_all_checks", lambda wiki_dir=None, fix=False: object())
    monkeypatch.setattr(runner, "format_report", lambda _report: "# Wiki Lint Report\n")


def _install_evolve_report(monkeypatch) -> None:
    import kb.evolve.analyzer as analyzer

    monkeypatch.setattr(
        analyzer,
        "generate_evolution_report",
        lambda wiki_dir=None: object(),
    )
    monkeypatch.setattr(
        analyzer,
        "format_evolution_report",
        lambda _report: "# Evolution Report\n",
    )


def test_kb_lint_feedback_scoped_to_wiki_dir(tmp_project, monkeypatch):
    from kb.feedback import store
    from kb.mcp.health import kb_lint

    _install_lint_report(monkeypatch)
    production_feedback = tmp_project / "production" / "feedback.json"
    _write_feedback(production_feedback, _feedback_with_low_trust_page("concepts/poison"))
    monkeypatch.setattr(store, "FEEDBACK_PATH", production_feedback)

    (tmp_project / "wiki" / "concepts" / "legit.md").write_text(
        "---\ntitle: Legit\n---\n\nLegit page.\n",
        encoding="utf-8",
    )

    report = kb_lint(wiki_dir=str(tmp_project / "wiki"))

    assert "Low-Trust Pages" not in report
    assert "concepts/poison" not in report
    scoped_feedback = tmp_project / ".data" / "feedback.json"
    if scoped_feedback.exists():
        assert json.loads(scoped_feedback.read_text(encoding="utf-8")) == {
            "entries": [],
            "page_scores": {},
        }


def test_kb_evolve_coverage_gaps_scoped_to_wiki_dir(tmp_project, monkeypatch):
    from kb.feedback import store
    from kb.mcp.health import kb_evolve

    _install_evolve_report(monkeypatch)
    production_feedback = tmp_project / "production" / "feedback.json"
    _write_feedback(
        production_feedback,
        _feedback_with_coverage_gap("What production-only page is missing?"),
    )
    monkeypatch.setattr(store, "FEEDBACK_PATH", production_feedback)

    (tmp_project / "wiki" / "concepts" / "legit.md").write_text(
        "---\ntitle: Legit\n---\n\nLegit page.\n",
        encoding="utf-8",
    )

    report = kb_evolve(wiki_dir=str(tmp_project / "wiki"))

    assert "Coverage Gaps" not in report
    assert "production-only" not in report
    assert "What production-only page is missing?" not in report


def test_kb_lint_wiki_dir_none_preserves_default(tmp_project, monkeypatch):
    from kb.feedback import store
    from kb.mcp.health import kb_lint

    _install_lint_report(monkeypatch)
    production_feedback = tmp_project / "production" / "feedback.json"
    _write_feedback(production_feedback, _feedback_with_low_trust_page("concepts/poison"))
    monkeypatch.setattr(store, "FEEDBACK_PATH", production_feedback)

    report = kb_lint()

    assert "Low-Trust Pages" in report
    assert "concepts/poison" in report
