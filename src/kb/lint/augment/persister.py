"""Persistence helpers for augment proposals, raw files, and page markers."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import frontmatter

from kb.utils.io import atomic_text_write
from kb.utils.pages import save_page_frontmatter

logger = logging.getLogger(__name__)


def _format_proposals_md(proposals: list[dict[str, Any]], run_id: str) -> str:
    """Render the proposals list as markdown for wiki/_augment_proposals.md."""
    lines = [
        f"# Augment Proposals - run `{run_id[:8]}`",
        f"Generated: {datetime.now(UTC).isoformat(timespec='seconds')}",
        "",
        "Review each proposal below; run `kb lint --augment --execute` to fetch + save to `raw/`.",
        "",
    ]
    for i, p in enumerate(proposals, 1):
        lines.append(f"## {i}. {p['stub_id']}")
        lines.append(f"- **Title:** {p['title']}")
        lines.append(f"- **Action:** {p['action']}")
        if p["action"] == "propose":
            lines.append("- **URLs:**")
            for u in p["urls"]:
                lines.append(f"  - {u}")
            lines.append(f"- **Rationale:** {p.get('rationale', '')}")
        else:
            lines.append(f"- **Reason:** {p.get('reason', '')}")
        lines.append("")
    return "\n".join(lines)


_PROPOSAL_HEADER_RE = re.compile(r"^##\s+\d+\.\s+(?P<stub_id>.+?)\s*$")
_PROPOSAL_TITLE_RE = re.compile(r"^-\s+\*\*Title:\*\*\s+(?P<title>.+?)\s*$")
_PROPOSAL_ACTION_RE = re.compile(r"^-\s+\*\*Action:\*\*\s+(?P<action>.+?)\s*$")
_PROPOSAL_URL_ITEM_RE = re.compile(r"^\s{2}-\s+(?P<url>\S+)\s*$")
_PROPOSAL_RATIONALE_RE = re.compile(r"^-\s+\*\*Rationale:\*\*\s*(?P<rationale>.*?)\s*$")
_PROPOSAL_REASON_RE = re.compile(r"^-\s+\*\*Reason:\*\*\s*(?P<reason>.*?)\s*$")


def _parse_proposals_md(proposals_path: Path) -> list[dict[str, Any]] | None:
    """Inverse of _format_proposals_md: parse markdown back into proposal dicts."""
    if not proposals_path.exists():
        return None
    try:
        text = proposals_path.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning("Could not read proposals file %s: %s", proposals_path, e)
        return None

    proposals: list[dict[str, Any]] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m_hdr = _PROPOSAL_HEADER_RE.match(lines[i])
        if not m_hdr:
            i += 1
            continue
        stub_id = m_hdr.group("stub_id").strip()
        entry: dict[str, Any] = {"stub_id": stub_id}
        i += 1
        in_urls_block = False
        while i < len(lines):
            line = lines[i]
            if _PROPOSAL_HEADER_RE.match(line):
                break
            m_title = _PROPOSAL_TITLE_RE.match(line)
            if m_title:
                entry["title"] = m_title.group("title").strip()
                in_urls_block = False
                i += 1
                continue
            m_action = _PROPOSAL_ACTION_RE.match(line)
            if m_action:
                entry["action"] = m_action.group("action").strip()
                in_urls_block = False
                i += 1
                continue
            if line.strip() == "- **URLs:**":
                entry.setdefault("urls", [])
                in_urls_block = True
                i += 1
                continue
            if in_urls_block:
                m_url = _PROPOSAL_URL_ITEM_RE.match(line)
                if m_url:
                    entry["urls"].append(m_url.group("url").strip())
                    i += 1
                    continue
                in_urls_block = False
            m_rat = _PROPOSAL_RATIONALE_RE.match(line)
            if m_rat:
                entry["rationale"] = m_rat.group("rationale").strip()
                i += 1
                continue
            m_reason = _PROPOSAL_REASON_RE.match(line)
            if m_reason:
                entry["reason"] = m_reason.group("reason").strip()
                i += 1
                continue
            i += 1

        if "title" in entry and "action" in entry:
            if entry["action"] == "propose" and not entry.get("urls"):
                logger.warning(
                    "Skipping proposal for %s: action=propose but no URLs parsed",
                    stub_id,
                )
                continue
            proposals.append(entry)
        else:
            logger.warning(
                "Skipping malformed proposal block for stub_id=%s (missing title or action)",
                stub_id,
            )

    return proposals if proposals else None


def _save_raw_file(
    *,
    raw_dir: Path,
    stub_id: str,
    title: str,
    url: str,
    run_id: str,
    content: str,
    proposer: str,
) -> Path:
    """Save fetched content to raw/articles/<slug>-<run_id[:8]>[-<n>].md."""
    from kb.utils.hashing import hash_bytes
    from kb.utils.text import slugify

    article_dir = raw_dir / "articles"
    article_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(title) or stub_id.split("/")[-1]
    base_name = f"{slug}-{run_id[:8]}.md"
    target = article_dir / base_name
    counter = 2
    while target.exists():
        target = article_dir / f"{slug}-{run_id[:8]}-{counter}.md"
        counter += 1

    sha = hash_bytes(content.encode("utf-8"))
    fm_lines = [
        "---",
        f"title: {title!r}",
        "source_type: article",
        f"fetched_from: {url}",
        f"fetched_at: {datetime.now(UTC).isoformat(timespec='seconds')}",
        "augment: true",
        f"augment_for: {stub_id}",
        f"augment_run_id: {run_id}",
        f"augment_proposer: {proposer}",
        f"sha256: '{sha}'",
        "---",
        "",
        "> [!untrusted_source]",
        f"> Auto-fetched from {url} during `kb lint --augment`. Not human-reviewed.",
        "",
        content,
    ]
    atomic_text_write("\n".join(fm_lines), target)
    return target


def _mark_page_augmented(page_path: Path, *, source_url: str) -> None:
    """Force ``confidence: speculative`` + prepend ``[!augmented]`` callout."""
    post = frontmatter.load(str(page_path))
    post.metadata["confidence"] = "speculative"
    callout = (
        "> [!augmented]\n"
        f"> Enriched from {source_url} on "
        f"{datetime.now(UTC).isoformat(timespec='seconds')}. "
        "Marked speculative until human review.\n\n"
    )
    if "[!augmented]" not in post.content:
        post.content = callout + post.content
    save_page_frontmatter(page_path, post)


def _record_attempt(stub_path: Path) -> None:
    """Stamp ``last_augment_attempted`` into the stub page's frontmatter."""
    if not stub_path.exists():
        return
    try:
        post = frontmatter.load(str(stub_path))
        post.metadata["last_augment_attempted"] = (
            datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        )
        save_page_frontmatter(stub_path, post)
    except Exception as e:
        logger.warning("Failed to record last_augment_attempted for %s: %s", stub_path, e)
