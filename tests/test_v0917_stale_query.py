"""Tests for stale truth flagging at query time (Phase 4)."""

import os
import time
from datetime import date, timedelta

from kb.query.engine import _flag_stale_results


class TestFlagStaleResults:
    def test_flags_page_with_newer_source(self, tmp_project, create_wiki_page, create_raw_source):
        old_date = (date.today() - timedelta(days=30)).isoformat()
        create_wiki_page(
            page_id="concepts/stale-topic",
            title="Stale Topic",
            content="Old content.",
            source_ref="raw/articles/new-source.md",
            updated=old_date,
            wiki_dir=tmp_project / "wiki",
        )
        # Create a raw source that is "newer" (mtime is now)
        create_raw_source("raw/articles/new-source.md", "Updated content.", tmp_project)

        results = [
            {
                "id": "concepts/stale-topic",
                "sources": ["raw/articles/new-source.md"],
                "updated": old_date,
                "score": 5.0,
            }
        ]
        flagged = _flag_stale_results(results, project_root=tmp_project)
        assert flagged[0].get("stale") is True

    def test_does_not_flag_fresh_page(self, tmp_project, create_wiki_page, create_raw_source):
        today = date.today().isoformat()
        create_wiki_page(
            page_id="concepts/fresh-topic",
            title="Fresh Topic",
            content="Fresh content.",
            source_ref="raw/articles/old-source.md",
            updated=today,
            wiki_dir=tmp_project / "wiki",
        )
        source_path = create_raw_source("raw/articles/old-source.md", "Source.", tmp_project)
        # Backdate the source file mtime to before the page updated date
        old_ts = time.time() - 86400 * 60
        os.utime(source_path, (old_ts, old_ts))

        results = [
            {
                "id": "concepts/fresh-topic",
                "sources": ["raw/articles/old-source.md"],
                "updated": today,
                "score": 5.0,
            }
        ]
        flagged = _flag_stale_results(results, project_root=tmp_project)
        assert flagged[0].get("stale") is False

    def test_handles_missing_source_gracefully(self):
        results = [
            {
                "id": "concepts/orphan",
                "sources": ["raw/articles/nonexistent.md"],
                "updated": date.today().isoformat(),
                "score": 5.0,
            }
        ]
        flagged = _flag_stale_results(results)
        assert flagged[0].get("stale") is False

    def test_handles_no_sources(self):
        results = [{"id": "concepts/no-src", "sources": [], "updated": "2026-04-12", "score": 1.0}]
        flagged = _flag_stale_results(results)
        assert flagged[0].get("stale") is False
