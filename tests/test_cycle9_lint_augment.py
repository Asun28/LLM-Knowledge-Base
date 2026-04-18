"""Cycle 9 augment summary regressions."""

from unittest.mock import patch


def test_summary_counts_per_stub_not_per_url(tmp_project, monkeypatch):
    from kb.lint.augment import _format_proposals_md, run_augment
    from kb.lint.fetcher import FetchResult

    wiki_dir = tmp_project / "wiki"
    raw_dir = tmp_project / "raw"
    monkeypatch.setattr("kb.lint._augment_manifest.MANIFEST_DIR", tmp_project / ".data")
    monkeypatch.setattr(
        "kb.lint._augment_rate.RATE_PATH", tmp_project / ".data" / "augment_rate.json"
    )

    proposals = [
        {
            "stub_id": "concepts/per-url-summary",
            "title": "Per URL Summary",
            "action": "propose",
            "urls": [
                "https://en.wikipedia.org/wiki/Per_url_summary_missing",
                "https://en.wikipedia.org/wiki/Per_url_summary",
            ],
            "rationale": "exercise failed then successful attempts",
        }
    ]
    (wiki_dir / "_augment_proposals.md").write_text(
        _format_proposals_md(proposals, "cycle9test"),
        encoding="utf-8",
    )

    class FakeFetcher:
        def __init__(self, *args, **kwargs):
            self.calls = 0

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return None

        def fetch(self, url):
            self.calls += 1
            if self.calls == 1:
                return FetchResult(
                    status="failed",
                    content=None,
                    extracted_markdown=None,
                    content_type="text/html",
                    bytes=0,
                    reason="HTTPStatusError: 404 Not Found",
                    url=url,
                )
            return FetchResult(
                status="ok",
                content="Per URL Summary source",
                extracted_markdown="Per URL Summary source text. " * 20,
                content_type="text/html",
                bytes=128,
                reason=None,
                url=url,
            )

    monkeypatch.setattr("kb.lint.fetcher.AugmentFetcher", FakeFetcher)

    with (
        patch(
            "kb.lint.augment.call_llm_json",
            side_effect=[
                {"score": 0.95},
                {
                    "title": "Per URL Summary",
                    "summary": "Source text for the per URL summary stub.",
                    "key_claims": ["summary counts are per stub"],
                    "entities_mentioned": [],
                    "concepts_mentioned": ["per-url-summary"],
                },
            ],
        ),
        patch("kb.ingest.pipeline.ingest_source") as ingest_source,
        patch("kb.lint.verdicts.add_verdict"),
        patch(
            "kb.lint.augment._post_ingest_quality",
            return_value=("pass", "stub enriched"),
        ),
    ):
        ingest_source.return_value = {
            "pages_created": ["concepts/per-url-summary"],
            "pages_updated": [],
        }
        result = run_augment(
            wiki_dir=wiki_dir,
            raw_dir=raw_dir,
            mode="auto_ingest",
            max_gaps=1,
        )

    assert "- Saved: 1, Skipped: 0, Failed: 0" in result["summary"]

    fetches = result["fetches"]
    assert fetches is not None
    assert [fetch["status"] for fetch in fetches] == ["failed", "saved"]

    ingests = result["ingests"]
    assert ingests is not None
    matching_ingests = [
        ingest for ingest in ingests if ingest["stub_id"] == "concepts/per-url-summary"
    ]
    assert matching_ingests == [
        {
            "stub_id": "concepts/per-url-summary",
            "status": "ingested",
            "pages_created": ["concepts/per-url-summary"],
            "pages_updated": [],
        }
    ]
