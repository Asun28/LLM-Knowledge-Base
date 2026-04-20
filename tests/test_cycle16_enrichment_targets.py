"""Cycle 16 AC4-AC6 — suggest_enrichment_targets ranks EXISTING pages by status.

Behavioural regressions — invoke production symbol directly; no source-scan
assertions (cycle-11 L2 Red Flag).
"""

from kb.evolve.analyzer import (
    format_evolution_report,
    generate_evolution_report,
    suggest_enrichment_targets,
)


def _make_page(page_id: str, status: str | None = None) -> dict:
    """Minimal page dict mirroring load_all_pages shape for enrichment inputs."""
    return {
        "id": page_id,
        "path": f"/fake/{page_id}.md",
        "title": page_id.replace("/", " ").replace("-", " ").title(),
        "type": "concept",
        "confidence": "stated",
        "sources": [],
        "created": "2026-04-01",
        "updated": "2026-04-01",
        "content": "",
        "status": "" if status is None else status,
        "belief_state": "",
        "authored_by": "",
    }


class TestSuggestEnrichmentTargets:
    def test_seed_before_developing_before_unknown_sort_order(self) -> None:
        """AC4 — status priority order: seed, developing, absent (sort last)."""
        pages = [
            _make_page("concepts/unknown", status=None),
            _make_page("concepts/developing-topic", status="developing"),
            _make_page("concepts/seed-topic", status="seed"),
        ]
        result = suggest_enrichment_targets(pages_dicts=pages)
        ids = [r["page_id"] for r in result]
        assert ids == [
            "concepts/seed-topic",
            "concepts/developing-topic",
            "concepts/unknown",
        ]

    def test_mature_and_evergreen_excluded(self) -> None:
        """AC4 — mature and evergreen are skipped (no enrichment needed)."""
        pages = [
            _make_page("concepts/mature-topic", status="mature"),
            _make_page("concepts/evergreen-topic", status="evergreen"),
            _make_page("concepts/seed-topic", status="seed"),
        ]
        result = suggest_enrichment_targets(pages_dicts=pages)
        ids = {r["page_id"] for r in result}
        assert ids == {"concepts/seed-topic"}

    def test_invalid_status_filtered(self) -> None:
        """T13 — injected / non-vocabulary status is dropped (defence-in-depth)."""
        pages = [
            _make_page("concepts/clean", status="seed"),
            _make_page("concepts/injected", status="<script>alert(1)</script>"),
            _make_page("concepts/typo", status="seeed"),  # not in PAGE_STATUSES
        ]
        result = suggest_enrichment_targets(pages_dicts=pages)
        ids = {r["page_id"] for r in result}
        assert ids == {"concepts/clean"}

    def test_includes_absent_status_sorted_last(self) -> None:
        """Q4 regression — absent status is INCLUDED, sorted LAST per AC4."""
        pages = [
            _make_page("concepts/absent-a", status=None),
            _make_page("concepts/seed-a", status="seed"),
            _make_page("concepts/absent-b", status=""),
            _make_page("concepts/developing-a", status="developing"),
        ]
        result = suggest_enrichment_targets(pages_dicts=pages)
        # Absent-status pages must be present AND sort after seed/developing.
        absent_ids = {r["page_id"] for r in result if r["status"] in ("", "<unknown>")}
        assert absent_ids == {"concepts/absent-a", "concepts/absent-b"}
        # They should be at the tail of the result list.
        last_two = [r["page_id"] for r in result[-2:]]
        assert set(last_two) == absent_ids

    def test_reason_has_per_status_hint(self) -> None:
        """AC4 — reason string is informative for common statuses."""
        pages = [
            _make_page("concepts/seed-x", status="seed"),
            _make_page("concepts/dev-y", status="developing"),
            _make_page("concepts/unknown-z", status=None),
        ]
        result = suggest_enrichment_targets(pages_dicts=pages)
        by_id = {r["page_id"]: r for r in result}
        assert "seed" in by_id["concepts/seed-x"]["reason"]
        assert "developing" in by_id["concepts/dev-y"]["reason"]
        assert by_id["concepts/unknown-z"]["status"] in ("", "<unknown>")

    def test_custom_status_priority_threads_through(self) -> None:
        """AC4 keyword-only — custom priority sequence drives ordering."""
        pages = [
            _make_page("concepts/s", status="seed"),
            _make_page("concepts/d", status="developing"),
        ]
        # Invert priority — developing first.
        result = suggest_enrichment_targets(
            pages_dicts=pages, status_priority=("developing", "seed")
        )
        assert [r["page_id"] for r in result] == ["concepts/d", "concepts/s"]


class TestGenerateEvolutionReportEnrichmentKey:
    def test_generate_evolution_report_has_enrichment_targets_key(self, tmp_wiki) -> None:
        """AC5 — returned dict exposes enrichment_targets key."""
        report = generate_evolution_report(wiki_dir=tmp_wiki)
        assert "enrichment_targets" in report
        assert isinstance(report["enrichment_targets"], list)

    def test_generate_evolution_report_has_status_priority_key(self, tmp_wiki) -> None:
        """AC6 — status_priority key present for downstream formatting."""
        report = generate_evolution_report(wiki_dir=tmp_wiki)
        assert "status_priority" in report
        assert list(report["status_priority"]) == ["seed", "developing"]


class TestFormatEvolutionReportEnrichmentSection:
    def _sample_report(self, targets: list[dict]) -> dict:
        return {
            "coverage": {"total_pages": 0, "by_type": {}, "under_covered_types": []},
            "connection_opportunities": [],
            "new_page_suggestions": [],
            "graph_stats": {"nodes": 0, "edges": 0, "components": 0},
            "flagged_pages": [],
            "enrichment_targets": targets,
            "status_priority": ["seed", "developing"],
            "recommendations": [],
        }

    def test_format_evolution_report_renders_section_when_nonempty(self) -> None:
        """AC6 — Enrichment targets section appears when list is non-empty."""
        report = self._sample_report(
            [{"page_id": "concepts/a", "status": "seed", "reason": "status=seed"}]
        )
        rendered = format_evolution_report(report)
        assert "### Enrichment targets" in rendered
        assert "concepts/a" in rendered

    def test_format_evolution_report_omits_section_when_empty(self) -> None:
        """AC6 — section absent when no enrichment targets."""
        report = self._sample_report([])
        rendered = format_evolution_report(report)
        assert "### Enrichment targets" not in rendered

    def test_format_evolution_report_includes_priority_sequence_inline(self) -> None:
        """AC6 (plan-gate amendment) — priority sequence appears inline in header."""
        report = self._sample_report([{"page_id": "concepts/x", "status": "seed", "reason": "r"}])
        rendered = format_evolution_report(report)
        assert "(seed, developing)" in rendered
