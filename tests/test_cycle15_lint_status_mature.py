"""Cycle 15 AC5/AC24 — check_status_mature_stale flags mature pages >90d stale."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from kb.lint.checks import check_status_mature_stale


def _write_page(
    wiki_dir: Path,
    pid: str,
    updated_days_ago: int,
    status: str | None,
    page_type: str = "concept",
) -> Path:
    updated = (date.today() - timedelta(days=updated_days_ago)).isoformat()
    subdir = {
        "summary": "summaries",
        "concept": "concepts",
        "entity": "entities",
    }[page_type]
    path = wiki_dir / subdir / f"{pid}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    status_line = f"status: {status}\n" if status is not None else ""
    path.write_text(
        f"""---
title: {pid}
source:
  - raw/articles/{pid}.md
created: 2026-01-01
updated: {updated}
type: {page_type}
confidence: stated
{status_line}---
body
""",
        encoding="utf-8",
    )
    return path


class TestMatureStale:
    def test_mature_91d_flagged(self, tmp_path):
        _write_page(tmp_path, "cap-theorem", 91, status="mature")
        issues = check_status_mature_stale(wiki_dir=tmp_path)
        assert len(issues) == 1
        assert issues[0]["check"] == "status_mature_stale"
        assert issues[0]["severity"] == "warning"
        assert "cap-theorem" in issues[0]["page"]

    def test_mature_89d_not_flagged(self, tmp_path):
        _write_page(tmp_path, "rag", 89, status="mature")
        issues = check_status_mature_stale(wiki_dir=tmp_path)
        assert issues == []

    def test_mature_365d_flagged(self, tmp_path):
        _write_page(tmp_path, "very-old", 365, status="mature")
        issues = check_status_mature_stale(wiki_dir=tmp_path)
        assert len(issues) == 1
        # Delta should be in the message.
        assert "365" in issues[0]["message"]


class TestOtherStatusesIgnored:
    """AC24 — only status=mature fires this check."""

    def test_seed_91d_not_flagged(self, tmp_path):
        _write_page(tmp_path, "seedling", 91, status="seed")
        assert check_status_mature_stale(wiki_dir=tmp_path) == []

    def test_developing_91d_not_flagged(self, tmp_path):
        _write_page(tmp_path, "developing", 91, status="developing")
        assert check_status_mature_stale(wiki_dir=tmp_path) == []

    def test_evergreen_91d_not_flagged(self, tmp_path):
        # evergreen is out-of-scope for the mature-stale check.
        _write_page(tmp_path, "evergreen", 91, status="evergreen")
        assert check_status_mature_stale(wiki_dir=tmp_path) == []

    def test_missing_status_not_flagged(self, tmp_path):
        _write_page(tmp_path, "no-status", 91, status=None)
        assert check_status_mature_stale(wiki_dir=tmp_path) == []


class TestTodayOverride:
    """AC24 — deterministic testing via `today` kwarg."""

    def test_today_kwarg_controls_cutoff(self, tmp_path):
        # Page updated 2026-01-01; today forced to 2026-04-30 → 119d delta.
        p = tmp_path / "concepts" / "fixed.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            """---
title: fixed
source:
  - raw/articles/x.md
created: 2026-01-01
updated: 2026-01-01
type: concept
confidence: stated
status: mature
---
body
""",
            encoding="utf-8",
        )
        issues = check_status_mature_stale(wiki_dir=tmp_path, today=date(2026, 4, 30))
        assert len(issues) == 1
        # 2026-04-30 - 2026-01-01 = 119 days
        assert "119" in issues[0]["message"]
