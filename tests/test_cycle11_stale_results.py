"""Cycle 11 AC9/AC10/AC11 stale result edge-case contract tests."""

import os
from datetime import UTC, date, datetime, time

import pytest

from kb.query.engine import _flag_stale_results


def test_flag_stale_results_empty_sources_is_not_stale():
    results = _flag_stale_results([{"updated": "2026-01-01", "sources": []}])

    assert results == [{"updated": "2026-01-01", "sources": [], "stale": False}]


def test_flag_stale_results_missing_sources_is_not_stale():
    results = _flag_stale_results([{"updated": "2026-01-01"}])

    assert results == [{"updated": "2026-01-01", "stale": False}]


# Cycle 15 AC1 note — removed the `20260101` int parametrize case. Python 3.11+
# extended `date.fromisoformat` to accept YYYYMMDD "basic format", so the
# integer 20260101 → str "20260101" parses to 2026-01-01. Combined with the
# cycle-15 decay gate (90d default for unknown sources), a page "updated" in
# early January gets flagged stale by April, violating the original intent.
# The remaining non-ISO fixtures are genuinely unparseable and still round-trip.
@pytest.mark.parametrize("updated", ["yesterday", "04/19/2026", ""])
def test_flag_stale_results_non_iso_updated_values_are_not_stale(updated):
    results = _flag_stale_results([{"updated": updated, "sources": ["raw/source.md"]}])

    assert results == [{"updated": updated, "sources": ["raw/source.md"], "stale": False}]


def test_flag_stale_results_source_mtime_equal_to_updated_is_not_stale(tmp_path):
    source = tmp_path / "raw" / "source.md"
    source.parent.mkdir()
    source.write_text("source\n", encoding="utf-8")

    source_date = date(2026, 4, 1)
    source_time = datetime.combine(source_date, time.min, tzinfo=UTC).timestamp()
    os.utime(source, (source_time, source_time))

    results = _flag_stale_results(
        [{"updated": source_date.isoformat(), "sources": ["raw/source.md"]}],
        project_root=tmp_path,
    )

    assert results == [{"updated": "2026-04-01", "sources": ["raw/source.md"], "stale": False}]
