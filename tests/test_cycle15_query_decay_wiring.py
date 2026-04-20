"""Cycle 15 AC1/AC20 — `_flag_stale_results` composes mtime + decay gates.

Two orthogonal staleness signals:
  1. Source mtime > page_date (pre-existing — wiki behind source).
  2. (today - page_date).days > max(decay_days_for per source) (new — source
     is old in absolute terms).

Stale if EITHER fires. Multi-source pages use lenient max over decay windows
(longest-decay platform wins).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from kb.query.engine import _flag_stale_results


def _page_with_source(pid: str, updated_days_ago: int, source_rels: list[str]) -> dict:
    today = date.today()
    updated = today - timedelta(days=updated_days_ago)
    return {
        "id": pid,
        "updated": updated.isoformat(),
        "sources": source_rels,
    }


def _seed_source_file(root: Path, rel: str, mtime_days_ago: int) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("stub source content", encoding="utf-8")
    ts = (datetime.now() - timedelta(days=mtime_days_ago)).timestamp()
    import os

    os.utime(p, (ts, ts))


class TestDecayGate:
    """AC20 — decay gate fires/does-not-fire per source platform."""

    def test_arxiv_1000d_not_flagged(self, tmp_path: Path):
        """arxiv (1095d decay) — 1000d-old page NOT flagged."""
        rel = "raw/papers/x.md"
        _seed_source_file(tmp_path, rel, mtime_days_ago=1005)
        r = _page_with_source("x", updated_days_ago=1000, source_rels=[rel])
        # Embed arxiv hostname so decay_days_for returns 1095d.
        r["sources"] = ["https://arxiv.org/abs/foo"]
        # Neutralise the mtime gate by dropping the filesystem lookup.
        out = _flag_stale_results([r], project_root=tmp_path)
        assert out[0]["stale"] is False, (
            "arxiv 1000d-old page must not be flagged under 1095d decay"
        )

    def test_github_200d_flagged(self, tmp_path: Path):
        """github (180d decay) — 200d-old page IS flagged."""
        r = _page_with_source(
            "gh", updated_days_ago=200, source_rels=["https://github.com/foo/bar"]
        )
        out = _flag_stale_results([r], project_root=tmp_path)
        assert out[0]["stale"] is True

    def test_multi_source_lenient_max(self, tmp_path: Path):
        """AC1 lenient max — page with arxiv + github sources 300d old NOT flagged.

        arxiv decay 1095d wins over github 180d; max = 1095 > 300 age.
        """
        r = _page_with_source(
            "mix",
            updated_days_ago=300,
            source_rels=[
                "https://github.com/foo/bar",
                "https://arxiv.org/abs/xyz",
            ],
        )
        out = _flag_stale_results([r], project_root=tmp_path)
        assert out[0]["stale"] is False, (
            "multi-source page with any long-decay source must not flag early"
        )

    def test_unknown_host_falls_back_to_default(self, tmp_path: Path):
        """Unknown source host → SOURCE_DECAY_DEFAULT_DAYS = 90 — 100d flags."""
        r = _page_with_source(
            "unknown", updated_days_ago=100, source_rels=["https://example.com/x"]
        )
        out = _flag_stale_results([r], project_root=tmp_path)
        assert out[0]["stale"] is True


class TestMtimeGatePreserved:
    """AC20 — existing mtime-vs-page-date semantic still fires."""

    def test_mtime_advances_past_page_date_flags(self, tmp_path: Path):
        """Source mtime newer than page updated → stale regardless of decay."""
        rel = "raw/articles/foo.md"
        _seed_source_file(tmp_path, rel, mtime_days_ago=1)
        r = _page_with_source("foo", updated_days_ago=60, source_rels=[rel])
        out = _flag_stale_results([r], project_root=tmp_path)
        assert out[0]["stale"] is True, (
            "mtime-vs-page-date still flags staleness even under no decay match"
        )

    def test_no_sources_no_flag(self, tmp_path: Path):
        """AC20 — page with empty sources list: no decay check, no mtime check."""
        r = {
            "id": "orphan",
            "updated": date.today().isoformat(),
            "sources": [],
        }
        out = _flag_stale_results([r], project_root=tmp_path)
        assert out[0]["stale"] is False

    def test_bad_updated_date_no_raise(self, tmp_path: Path):
        """AC20 — unparseable `updated` field doesn't raise; returns stale=False."""
        r = {
            "id": "bad",
            "updated": "not-a-date",
            "sources": ["https://arxiv.org/abs/y"],
        }
        out = _flag_stale_results([r], project_root=tmp_path)
        assert out[0]["stale"] is False
