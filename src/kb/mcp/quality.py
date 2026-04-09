"""Quality MCP tools — review, refine, lint deep, consistency, feedback, verdicts, page creation."""

import logging
from datetime import date

from kb.config import CONFIDENCE_LEVELS, PAGE_TYPES, WIKI_DIR, WIKI_SUBDIR_TO_TYPE
from kb.mcp.app import _validate_page_id, mcp
from kb.utils.pages import load_all_pages
from kb.utils.text import yaml_escape

logger = logging.getLogger(__name__)


@mcp.tool()
def kb_review_page(page_id: str) -> str:
    """Review a wiki page — returns page content, raw sources, and review checklist.

    The tool returns raw context (text). You (Claude Code) or a wiki-reviewer
    sub-agent evaluate the context and produce a structured JSON review.

    Args:
        page_id: Page to review (e.g., 'concepts/rag').
    """
    err = _validate_page_id(page_id)
    if err:
        return f"Error: {err}"

    try:
        from kb.review.context import build_review_context

        return build_review_context(page_id)
    except FileNotFoundError as e:
        return f"Error reviewing {page_id}: {e}"
    except Exception as e:
        logger.exception("Unexpected error reviewing %s", page_id)
        return f"Error reviewing {page_id}: {e}"


@mcp.tool()
def kb_refine_page(page_id: str, updated_content: str, revision_notes: str = "") -> str:
    """Update a wiki page's content while preserving frontmatter.

    Used after review or self-critique to apply improvements.
    Logs to wiki/log.md and .data/review_history.json.

    Args:
        page_id: Page to update (e.g., 'concepts/rag').
        updated_content: New markdown body (frontmatter preserved automatically).
        revision_notes: What changed and why.
    """
    err = _validate_page_id(page_id)
    if err:
        return f"Error: {err}"

    try:
        from kb.review.refiner import refine_page

        result = refine_page(page_id, updated_content, revision_notes)
    except Exception as e:
        logger.exception("Unexpected error refining %s", page_id)
        return f"Error refining {page_id}: {e}"
    if "error" in result:
        return f"Error: {result['error']}"

    # Include affected pages in response (fail-safe)
    try:
        from kb.compile.linker import build_backlinks

        backlinks = build_backlinks()
        affected = backlinks.get(page_id, [])
    except Exception:
        logger.debug("Failed to compute backlinks for %s after refine", page_id, exc_info=True)
        affected = []

    lines = [
        f"Refined: {page_id}",
        f"Notes: {revision_notes}",
    ]
    if affected:
        lines.append(f"Affected pages ({len(affected)} — may need review):")
        for p in affected:
            lines.append(f"  - {p}")
    return "\n".join(lines)


@mcp.tool()
def kb_lint_deep(page_id: str) -> str:
    """Deep lint a single page — returns page + raw sources side-by-side
    for source fidelity evaluation.

    You (Claude Code) evaluate whether each claim traces to the source.

    Args:
        page_id: Page to check (e.g., 'concepts/rag').
    """
    err = _validate_page_id(page_id)
    if err:
        return f"Error: {err}"

    try:
        from kb.lint.semantic import build_fidelity_context

        return build_fidelity_context(page_id)
    except FileNotFoundError as e:
        return f"Error checking fidelity for {page_id}: {e}"
    except Exception as e:
        logger.exception("Unexpected error in lint_deep for %s", page_id)
        return f"Error checking fidelity for {page_id}: {e}"


@mcp.tool()
def kb_lint_consistency(page_ids: str = "") -> str:
    """Cross-page consistency check — returns related pages grouped for
    contradiction detection.

    Pass comma-separated page IDs, or leave empty to auto-select
    pages most likely to conflict (shared sources, wikilink neighbors).

    Args:
        page_ids: Comma-separated page IDs (e.g., 'concepts/rag,concepts/llm').
                  Empty = auto-select groups.
    """
    try:
        from kb.lint.semantic import build_consistency_context

        ids = [p.strip() for p in page_ids.split(",") if p.strip()] if page_ids else None
        if ids:
            for pid in ids:
                err = _validate_page_id(pid, check_exists=True)
                if err:
                    return f"Error: {err}"
        return build_consistency_context(ids)
    except Exception as e:
        logger.exception("Error running consistency check")
        return f"Error running consistency check: {e}"


@mcp.tool()
def kb_query_feedback(question: str, rating: str, cited_pages: str = "", notes: str = "") -> str:
    """Record feedback on a query answer to improve wiki reliability.

    Args:
        question: The question that was asked.
        rating: 'useful', 'wrong', or 'incomplete'.
        cited_pages: Comma-separated page IDs cited in the answer.
        notes: What was wrong or missing.
    """
    from kb.feedback.store import add_feedback_entry

    pages = [p.strip() for p in cited_pages.split(",") if p.strip()]
    try:
        add_feedback_entry(question, rating, pages, notes)
    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        logger.exception("Error storing feedback for question: %s", question)
        return f"Error: Failed to store feedback — {e}"

    action = {
        "useful": "Trust scores boosted for cited pages.",
        "wrong": "Cited pages flagged for priority re-lint.",
        "incomplete": "Coverage gap logged for kb_evolve.",
    }
    return f"Feedback recorded: {rating}\n{action.get(rating, '')}"


@mcp.tool()
def kb_reliability_map() -> str:
    """Show page trust scores based on query feedback history.

    Pages cited in successful queries score higher.
    Pages cited in wrong answers score lower and are flagged for re-lint.
    """
    try:
        from kb.feedback.reliability import compute_trust_scores, get_flagged_pages

        scores = compute_trust_scores()
        if not scores:
            return "No feedback recorded yet. Use kb_query_feedback after queries."

        sorted_pages = sorted(scores.items(), key=lambda x: x[1].get("trust", 0.5), reverse=True)
        flagged = set(get_flagged_pages())
    except Exception as e:
        logger.exception("Error computing reliability map")
        return f"Error computing reliability map: {e}"

    lines = ["# Page Reliability Map\n"]
    for pid, s in sorted_pages:
        flag = " **[FLAGGED]**" if pid in flagged else ""
        lines.append(
            f"- {pid}: trust={s['trust']:.2f} "
            f"(useful={s['useful']}, wrong={s['wrong']}, incomplete={s['incomplete']}){flag}"
        )

    if flagged:
        lines.append(
            f"\n**{len(flagged)} page(s) flagged** (trust <= 0.4). Run kb_lint_deep on these."
        )

    return "\n".join(lines)


@mcp.tool()
def kb_affected_pages(page_id: str) -> str:
    """Find pages affected when this page changes.

    Returns pages that link TO this page (backlinks) and pages
    that share the same raw sources. Use after updating a page
    to decide whether related pages need review.

    Args:
        page_id: Page that was changed (e.g., 'concepts/rag').
    """
    err = _validate_page_id(page_id, check_exists=False)
    if err:
        return f"Error: {err}"

    try:
        from kb.compile.linker import build_backlinks

        backlinks_map = build_backlinks()
        back = backlinks_map.get(page_id, [])
    except Exception as e:
        logger.exception("Error building backlinks for %s", page_id)
        return f"Error computing affected pages: {e}"

    # Find pages sharing same sources using the shared page loader
    shared_source_pages: list[str] = []
    try:
        all_pages = load_all_pages()
        this_page = next((p for p in all_pages if p["id"] == page_id), None)

        if this_page:
            page_sources = this_page["sources"]
            for other in all_pages:
                if other["id"] == page_id:
                    continue
                if set(page_sources) & set(other["sources"]):
                    shared_source_pages.append(other["id"])
    except Exception as e:
        logger.debug("Failed to compute shared sources for %s: %s", page_id, e)

    all_affected = sorted(set(back + shared_source_pages))

    if not all_affected:
        return f"No pages are affected by changes to {page_id}."

    lines = [
        f"# Pages Affected by Changes to {page_id}\n",
        f"**Total:** {len(all_affected)} page(s)\n",
    ]

    if back:
        lines.append(f"## Backlinks ({len(back)} pages link to this page)")
        for p in back:
            lines.append(f"  - {p}")

    if shared_source_pages:
        lines.append(f"\n## Shared Sources ({len(shared_source_pages)} pages share raw sources)")
        for p in shared_source_pages:
            lines.append(f"  - {p}")

    lines.append("\nReview these pages if the changes affect shared claims or definitions.")

    return "\n".join(lines)


# ── New v0.7.0 Tools ──────────────────────────────────────────────


@mcp.tool()
def kb_save_lint_verdict(
    page_id: str,
    verdict_type: str,
    verdict: str,
    issues: str = "",
    notes: str = "",
) -> str:
    """Record a lint or review verdict for a wiki page.

    Use after evaluating kb_lint_deep, kb_lint_consistency, or kb_review_page
    results to store the verdict persistently.

    Args:
        page_id: Page that was evaluated (e.g., 'concepts/rag').
        verdict_type: Type of check: 'fidelity', 'consistency', 'completeness', or 'review'.
        verdict: Result: 'pass', 'fail', or 'warning'.
        issues: Optional JSON array of issue objects with severity/description.
        notes: Free-text notes about the evaluation.
    """
    err = _validate_page_id(page_id, check_exists=False)
    if err:
        return f"Error: {err}"

    import json

    from kb.lint.verdicts import add_verdict

    issue_list = None
    if issues:
        try:
            issue_list = json.loads(issues)
            if not isinstance(issue_list, list):
                return "Error: issues must be a JSON array."
        except json.JSONDecodeError as e:
            return f"Error: Invalid issues JSON — {e}"

    try:
        entry = add_verdict(page_id, verdict_type, verdict, issue_list, notes)
    except ValueError as e:
        return f"Error: {e}"

    return (
        f"Verdict recorded for {page_id}:\n"
        f"  Type: {verdict_type}\n"
        f"  Verdict: {verdict}\n"
        f"  Issues: {len(entry['issues'])}\n"
        f"  Notes: {notes or '(none)'}"
    )


@mcp.tool()
def kb_create_page(
    page_id: str,
    title: str,
    content: str,
    page_type: str = "",
    confidence: str = "inferred",
    source_refs: str = "",
) -> str:
    """Create a new wiki page directly (for comparisons, synthesis, or any type).

    Use when the page isn't generated by ingestion — e.g., comparison pages
    that analyze multiple concepts, or synthesis pages that draw conclusions
    across sources.

    Args:
        page_id: Full page ID (e.g., 'comparisons/rag-vs-fine-tuning').
        title: Page title.
        content: Markdown body content (frontmatter added automatically).
        page_type: Page type. Auto-detected from page_id path if empty.
                   One of: entity, concept, comparison, synthesis, summary.
        confidence: Confidence level: 'stated', 'inferred', or 'speculative'.
        source_refs: Comma-separated source references (e.g., 'raw/articles/a.md,raw/papers/b.md').
    """
    # Validate page_id — reuse shared validator (handles traversal + resolve check)
    if "/" not in page_id:
        return "Error: page_id must include subdirectory (e.g., 'comparisons/rag-vs-finetuning')."
    err = _validate_page_id(page_id, check_exists=False)
    if err:
        return f"Error: {err}"
    if not title or not title.strip():
        return "Error: Title cannot be empty."

    page_path = WIKI_DIR / f"{page_id}.md"
    if page_path.exists():
        return f"Error: Page already exists: {page_id}. Use kb_refine_page to update."

    # Auto-detect type from path
    if not page_type:
        subdir = page_id.split("/")[0]
        page_type = WIKI_SUBDIR_TO_TYPE.get(subdir, "")
        if not page_type:
            return (
                f"Error: Cannot detect type from '{subdir}/'. "
                f"Specify page_type: {', '.join(PAGE_TYPES)}"
            )

    if page_type not in PAGE_TYPES:
        return f"Error: Invalid page_type '{page_type}'. Use one of: {', '.join(PAGE_TYPES)}"

    if confidence not in CONFIDENCE_LEVELS:
        valid = ", ".join(CONFIDENCE_LEVELS)
        return f"Error: Invalid confidence '{confidence}'. Use one of: {valid}"

    # Build source list
    sources = [s.strip() for s in source_refs.split(",") if s.strip()] if source_refs else []

    # Validate source refs — reject path traversal
    for src in sources:
        if ".." in src or src.startswith("/") or src.startswith("\\"):
            return (
                f"Error: Invalid source_ref '{src}'. "
                "Must not contain '..' or start with '/' or '\\'."
            )

    # Write page with frontmatter
    today = date.today().isoformat()
    safe_title = yaml_escape(title)

    source_lines = ""
    if sources:
        source_entries = "\n".join(f'  - "{yaml_escape(s)}"' for s in sources)
        source_lines = f"source:\n{source_entries}"
    else:
        source_lines = "source: []"

    frontmatter = f"""---
title: "{safe_title}"
{source_lines}
created: {today}
updated: {today}
type: {page_type}
confidence: {confidence}
---

"""

    try:
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(frontmatter + content, encoding="utf-8")
    except OSError as e:
        return f"Error: Failed to write page: {e}"

    # Log
    try:
        from kb.utils.wiki_log import append_wiki_log

        append_wiki_log("create", f"Created {page_id} ({page_type}, {confidence})")
    except OSError as e:
        logger.warning("Failed to append wiki log after creating %s: %s", page_id, e)

    return (
        f"Created: {page_id}\n"
        f"  Type: {page_type}\n"
        f"  Confidence: {confidence}\n"
        f"  Sources: {len(sources)}"
    )
