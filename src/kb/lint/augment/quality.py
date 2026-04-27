"""Post-ingest quality checks and augment outcome accounting."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import frontmatter

from kb import config
from kb.lint.checks import check_stub_pages
from kb.utils.pages import save_page_frontmatter


def _package_attr(name: str, fallback: Any) -> Any:
    package = sys.modules.get("kb.lint.augment")
    return getattr(package, name, fallback) if package is not None else fallback


def _count_final_stub_outcomes(
    *,
    proposals: list[dict[str, Any]],
    ingests: list[dict[str, Any]] | None,
    verdicts: list[dict[str, Any]] | None,
    manifest: Any | None,
) -> tuple[int, int, int]:
    """Return saved/skipped/failed counts from final per-stub state only."""
    saved = 0
    skipped = 0
    failed = 0

    verdict_by_stub = {v["stub_id"]: v for v in verdicts or []}
    ingest_by_stub = {i["stub_id"]: i for i in ingests or []}

    if manifest is not None:
        for gap in manifest.data.get("gaps", []):
            stub_id = gap.get("page_id")
            verdict = verdict_by_stub.get(stub_id)
            if verdict is not None and verdict.get("verdict") == "fail":
                failed += 1
                continue
            state = gap.get("state")
            if state in {"done", "saved", "ingested", "verdict"}:
                saved += 1
            elif state in {"abstained", "cooldown"}:
                skipped += 1
            else:
                failed += 1
        return saved, skipped, failed

    if ingests is not None:
        for ingest in ingest_by_stub.values():
            status = ingest.get("status")
            if status in {"ingested", "saved"}:
                saved += 1
            elif status in {"skipped", "dry_run_skipped"}:
                skipped += 1
            else:
                failed += 1
        return saved, skipped, failed

    skipped = len(proposals)
    return saved, skipped, failed


def _resolve_raw_dir(wiki_dir: Path, raw_dir: Path | None) -> Path:
    """Derive raw_dir from wiki_dir override when omitted."""
    wiki_root = _package_attr("WIKI_DIR", config.WIKI_DIR)
    raw_root = _package_attr("RAW_DIR", config.RAW_DIR)
    if raw_dir is None and wiki_dir != wiki_root:
        return wiki_dir.parent / "raw"
    return raw_dir or raw_root


def _record_verdict_gap_callout(stub_path: Path, *, run_id: str, reason: str) -> None:
    """Prepend a ``[!gap]`` callout to a stub page after a failed augment verdict."""
    if not stub_path.exists():
        return
    post = frontmatter.load(str(stub_path))
    gap_callout = (
        f"> [!gap]\n"
        f"> Augment run {run_id[:8]} failed quality check: "
        f"{reason}. Manual review needed.\n\n"
    )
    if "[!gap]" not in post.content:
        post.content = gap_callout + post.content
        save_page_frontmatter(stub_path, post)


def _post_ingest_quality(*, page_path: Path, wiki_dir: Path) -> tuple[str, str]:
    """Targeted post-ingest quality regression: did the augment actually help?"""
    if not page_path.exists():
        return "fail", "page not found post-ingest"

    stub_issues = check_stub_pages(wiki_dir=wiki_dir, pages=[page_path])
    if stub_issues:
        return (
            "fail",
            f"page still a stub after augment ({stub_issues[0]['content_length']} chars)",
        )

    try:
        post = frontmatter.load(str(page_path))
    except Exception as e:
        return "fail", f"frontmatter unparseable: {e}"

    sources = post.metadata.get("source") or []
    if isinstance(sources, str):
        sources = [sources]
    if not sources:
        return "fail", "augmented page has no source: in frontmatter"

    return "pass", f"body len ok, {len(sources)} source(s)"
