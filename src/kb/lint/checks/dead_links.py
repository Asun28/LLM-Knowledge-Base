"""Dead-link lint checks."""

import re
from pathlib import Path

from kb.compile.linker import _mask_code_blocks, _unmask_code_blocks
from kb.lint import checks


def check_dead_links(wiki_dir: Path | None = None) -> list[dict]:
    """Find wikilinks pointing to non-existent pages.

    Cycle 7 AC18: ``[[index]]`` / ``[[_sources]]`` / ``[[log]]`` wikilinks are
    not dead when the corresponding root-level file exists. ``scan_wiki_pages``
    only walks ``WIKI_SUBDIRS`` and thus never includes root index files in
    ``existing_ids`` — without this filter every page linking ``[[index]]``
    generates a false-positive dead-link issue.

    Returns:
        List of dicts: {source, target, message}.
    """
    wiki_dir = wiki_dir or checks.WIKI_DIR
    result = checks.resolve_wikilinks(wiki_dir)

    # Stem → filename map for root files that count as valid link targets.
    _ROOT_TARGETS = {name.removesuffix(".md"): name for name in _INDEX_FILES}

    issues = []
    for broken in result["broken"]:
        target = broken["target"]
        # AC18: honour root-level index files if present on disk.
        if target in _ROOT_TARGETS and (wiki_dir / _ROOT_TARGETS[target]).is_file():
            continue
        issues.append(
            {
                "check": "dead_link",
                "severity": "error",
                "page": broken["source"],
                "target": target,
                "message": f"Broken wikilink: [[{target}]] in {broken['source']}",
            }
        )
    return issues


def fix_dead_links(
    wiki_dir: Path | None = None,
    broken_links: list[dict] | None = None,
) -> list[dict]:
    """Fix broken wikilinks by replacing them with plain text.

    ``[[broken/link]]`` becomes ``broken/link`` (basename if path contains ``/``).
    ``[[broken/link|Display Text]]`` becomes ``Display Text``.

    Args:
        wiki_dir: Path to wiki directory.
        broken_links: Pre-computed list of broken link dicts (with 'source' and 'target' keys).
            If None, resolve_wikilinks() is called to compute them (avoids duplicate call
            when run_all_checks already computed the broken links).

    Returns:
        List of dicts: {check, severity, page, target, message} for each fix applied.
    """
    wiki_dir = wiki_dir or checks.WIKI_DIR
    if broken_links is None:
        result = checks.resolve_wikilinks(wiki_dir)
        broken_links = result["broken"]
    fixes: list[dict] = []

    # Group broken links by source page
    broken_by_page: dict[str, list[str]] = {}
    for broken in broken_links:
        broken_by_page.setdefault(broken["source"], []).append(broken["target"])

    for source_pid, targets in broken_by_page.items():
        page_path = wiki_dir / f"{source_pid}.md"
        if not page_path.exists():
            continue

        content = page_path.read_text(encoding="utf-8")
        # Mask code blocks to prevent modifying wikilinks inside code examples
        content, masked_code, mask_prefix = _mask_code_blocks(content)
        modified = False

        for target in targets:
            old_content = content

            # Match [[target|display]] or [[target]]
            # Use re.IGNORECASE since extract_wikilinks lowercases targets
            pattern = re.compile(r"\[\[" + re.escape(target) + r"\|([^\]]+)\]\]", re.IGNORECASE)
            if pattern.search(content):
                content = pattern.sub(r"\1", content)
            else:
                # No display text — replace [[target]] with target basename
                pattern_plain = re.compile(r"\[\[" + re.escape(target) + r"\]\]", re.IGNORECASE)
                display = target.split("/")[-1] if "/" in target else target
                content = pattern_plain.sub(display, content)

            # Only record a fix if the content actually changed
            if content != old_content:
                modified = True
                fixes.append(
                    {
                        "check": "dead_link_fixed",
                        "severity": "info",
                        "page": source_pid,
                        "target": target,
                        "message": f"Fixed broken wikilink [[{target}]] in {source_pid}",
                    }
                )

        # Unmask code blocks before writing
        content = _unmask_code_blocks(content, masked_code, mask_prefix)
        if modified:
            checks.atomic_text_write(content, page_path)

    # Log fixes to audit trail
    if fixes:
        from kb.utils.wiki_log import append_wiki_log

        fixed_count = len(fixes)
        pages_fixed = len({f["page"] for f in fixes})
        effective_log_dir = wiki_dir if wiki_dir is not None else checks.WIKI_DIR
        append_wiki_log(
            "lint-fix",
            f"Auto-fixed {fixed_count} broken wikilink(s) across {pages_fixed} page(s)",
            effective_log_dir / "log.md",
        )

    return fixes


# _categories.md was designed but never written by the system — dropped to
# avoid a dead lookup on every lint invocation. Re-add if/when the categories
# index is actually materialized by the compile pipeline.
_INDEX_FILES = ("index.md", "_sources.md", "log.md")
