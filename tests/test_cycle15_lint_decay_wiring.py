"""Cycle 15 AC4/AC23 — `check_staleness` wired to per-source decay_days_for.

Tests:
  - Per-platform decay: arxiv page 1000d old NOT flagged; github page 200d flagged.
  - Multi-source lenient max: page with arxiv + github sources 300d old NOT flagged.
  - Explicit max_days kwarg overrides per-page decay for every page.
  - Pages with no sources fall back to SOURCE_DECAY_DEFAULT_DAYS.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from kb.lint.checks import check_staleness


def _write_page(
    wiki_dir: Path,
    pid: str,
    updated_days_ago: int,
    sources: list[str],
    page_type: str = "concept",
) -> Path:
    updated = (date.today() - timedelta(days=updated_days_ago)).isoformat()
    subdir = {
        "summary": "summaries",
        "concept": "concepts",
        "entity": "entities",
        "comparison": "comparisons",
        "synthesis": "synthesis",
    }[page_type]
    path = wiki_dir / subdir / f"{pid}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    src_yaml = "\n".join(f"  - {s}" for s in sources)
    path.write_text(
        f"""---
title: {pid}
source:
{src_yaml}
created: 2026-01-01
updated: {updated}
type: {page_type}
confidence: stated
---
body
""",
        encoding="utf-8",
    )
    return path


class TestPerSourceDecay:
    """AC23 — per-source decay via decay_days_for."""

    def test_arxiv_1000d_not_flagged(self, tmp_path):
        _write_page(tmp_path, "arxiv-paper", 1000, ["https://arxiv.org/abs/2401.12345"])
        issues = check_staleness(wiki_dir=tmp_path)
        assert not any(i["check"] == "stale_page" for i in issues), (
            "arxiv source (1095d decay) should not flag 1000d-old page"
        )

    def test_github_200d_flagged(self, tmp_path):
        _write_page(tmp_path, "gh-repo", 200, ["https://github.com/foo/bar"])
        issues = check_staleness(wiki_dir=tmp_path)
        stale = [i for i in issues if i["check"] == "stale_page"]
        assert len(stale) == 1
        assert stale[0]["page"].endswith("gh-repo")

    def test_github_150d_not_flagged(self, tmp_path):
        _write_page(tmp_path, "gh-fresh", 150, ["https://github.com/foo/bar"])
        issues = check_staleness(wiki_dir=tmp_path)
        assert not any(i["check"] == "stale_page" for i in issues)

    def test_multi_source_lenient_max(self, tmp_path):
        """Page with arxiv + github sources 300d old NOT flagged (arxiv wins)."""
        _write_page(
            tmp_path,
            "mixed",
            300,
            ["https://github.com/foo/bar", "https://arxiv.org/abs/xyz"],
        )
        issues = check_staleness(wiki_dir=tmp_path)
        assert not any(i["check"] == "stale_page" for i in issues), (
            "multi-source page must use max(decay) across sources"
        )


class TestExplicitMaxDaysOverride:
    """AC4 — caller-provided max_days kwarg forces every page to that window."""

    def test_max_days_30_flags_60d_arxiv(self, tmp_path):
        """Even arxiv (1095d decay) flags at 60d when caller forces max_days=30."""
        _write_page(tmp_path, "arxiv-tight", 60, ["https://arxiv.org/abs/2401.12345"])
        issues = check_staleness(wiki_dir=tmp_path, max_days=30)
        assert any(i["check"] == "stale_page" for i in issues), (
            "explicit max_days=30 should override per-page decay"
        )

    def test_max_days_none_uses_per_page(self, tmp_path):
        """Default (max_days=None) uses per-page decay."""
        _write_page(tmp_path, "arxiv-tight", 60, ["https://arxiv.org/abs/2401.12345"])
        issues = check_staleness(wiki_dir=tmp_path)  # max_days defaults to None
        assert not any(i["check"] == "stale_page" for i in issues)


class TestNoSourceFallback:
    """AC4 — pages with no sources fall back to SOURCE_DECAY_DEFAULT_DAYS (90)."""

    def test_no_sources_flags_at_100d(self, tmp_path):
        """Empty source list → 90d default; 100d-old page flagged."""
        # Write page manually with empty source field.
        updated = (date.today() - timedelta(days=100)).isoformat()
        p = tmp_path / "concepts" / "orphan.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            f"""---
title: orphan
source: []
created: 2026-01-01
updated: {updated}
type: concept
confidence: stated
---
body
""",
            encoding="utf-8",
        )
        issues = check_staleness(wiki_dir=tmp_path)
        assert any(i["check"] == "stale_page" for i in issues)

    def test_no_sources_not_flagged_at_60d(self, tmp_path):
        updated = (date.today() - timedelta(days=60)).isoformat()
        p = tmp_path / "concepts" / "orphan2.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            f"""---
title: orphan2
source: []
created: 2026-01-01
updated: {updated}
type: concept
confidence: stated
---
body
""",
            encoding="utf-8",
        )
        issues = check_staleness(wiki_dir=tmp_path)
        assert not any(i["check"] == "stale_page" for i in issues)
