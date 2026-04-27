"""Compile MCP tools — scan raw sources and run wiki compilation."""

import logging

from kb.mcp.app import _rel, _validate_wiki_dir, mcp
from kb.utils.sanitize import sanitize_error_text

logger = logging.getLogger(__name__)

_LEGACY_SYNC_NAMES = (
    "_rel",
    "_validate_wiki_dir",
    "logger",
    "sanitize_error_text",
)


def _refresh_legacy_bindings() -> None:
    """Honor legacy monkeypatches made through ``kb.mcp.core``."""
    import kb.mcp.core as core

    for name in _LEGACY_SYNC_NAMES:
        if hasattr(core, name):
            globals()[name] = getattr(core, name)


@mcp.tool()
def kb_compile_scan(incremental: bool = True, wiki_dir: str | None = None) -> str:
    """Scan for new/changed raw sources that need ingestion.

    Returns source files to process. For each, call kb_ingest with extraction_json.
    Note: each call also writes current template hashes to the hash manifest.

    Args:
        incremental: If True (default), only new/changed sources. If False, all.
        wiki_dir: Optional wiki directory override. When provided, raw sources
            and the hash manifest are resolved from the same project root.
    """
    _refresh_legacy_bindings()
    try:
        from kb.compile.compiler import find_changed_sources, scan_raw_sources
    except Exception as e:
        return f"Error loading compile module: {sanitize_error_text(e)}"

    try:
        wiki_path, err = _validate_wiki_dir(wiki_dir)
        if err:
            return f"Error: {err}"
        raw_dir = wiki_path.parent / "raw" if wiki_path else None
        manifest_path = wiki_path.parent / ".data" / "hashes.json" if wiki_path else None
        if incremental:
            # save_hashes=True (default): marks templates as seen so repeated calls
            # to kb_compile_scan de-duplicate work between invocations.
            new_sources, changed_sources = find_changed_sources(
                raw_dir=raw_dir, manifest_path=manifest_path
            )
            if not new_sources and not changed_sources:
                return "No new or changed sources found. Wiki is up to date."

            lines = ["# Compile Scan (incremental)\n"]
            if new_sources:
                lines.append(f"## New sources ({len(new_sources)})\n")
                for s in new_sources:
                    lines.append(f"- {_rel(s)}")
            if changed_sources:
                lines.append(f"\n## Changed sources ({len(changed_sources)})\n")
                for s in changed_sources:
                    lines.append(f"- {_rel(s)}")

            total = len(new_sources) + len(changed_sources)
            lines.append(
                f"\n**Total: {total} source(s) to process.** "
                "For each: call kb_ingest(source_path) to get the extraction prompt, "
                "then call kb_ingest(source_path, extraction_json=...) with your extraction."
            )
        else:
            all_sources = scan_raw_sources(raw_dir=raw_dir)
            if not all_sources:
                return "No source files found in raw/."
            lines = [
                "# Compile Scan (full)\n",
                f"**Total: {len(all_sources)} source(s)**\n",
            ]
            for s in all_sources:
                lines.append(f"- {_rel(s)}")
            lines.append(
                "\nFor each: call kb_ingest(source_path) to get the extraction prompt, "
                "then call kb_ingest(source_path, extraction_json=...) with your extraction."
            )
    except Exception as e:
        return f"Error scanning sources: {sanitize_error_text(e)}"

    return "\n".join(lines)


@mcp.tool()
def kb_compile(incremental: bool = True) -> str:
    """Compile wiki pages from raw sources.

    In incremental mode, only processes new and changed sources.
    In full mode, recompiles everything.

    Note: Each source requires LLM extraction (ANTHROPIC_API_KEY needed).
    For Claude Code mode, use kb_compile_scan() to get the list, then
    kb_ingest() each source with your own extraction.

    Args:
        incremental: If True (default), only new/changed sources. If False, all.
    """
    _refresh_legacy_bindings()
    try:
        from kb.compile.compiler import compile_wiki

        result = compile_wiki(incremental=incremental)
    except Exception as e:
        logger.exception("Error running compile")
        return f"Error running compile: {sanitize_error_text(e)}"

    mode = result["mode"]
    lines = [
        f"# Compile Complete ({mode})\n",
        f"**Sources processed:** {result['sources_processed']}",
        f"**Pages created:** {len(result['pages_created'])}",
        f"**Pages updated:** {len(result['pages_updated'])}",
    ]
    if result["pages_created"]:
        lines.append("\n## Created")
        for p in result["pages_created"]:
            lines.append(f"  + {p}")
    if result["pages_updated"]:
        lines.append("\n## Updated")
        for p in result["pages_updated"]:
            lines.append(f"  ~ {p}")
    if result.get("pages_skipped"):
        lines.append(f"\n## Skipped ({len(result['pages_skipped'])})")
        for p in result["pages_skipped"]:
            lines.append(f"  ! {p}")
    if result.get("wikilinks_injected"):
        lines.append(f"\n## Wikilinks Injected ({len(result['wikilinks_injected'])})")
        for p in result["wikilinks_injected"]:
            lines.append(f"  -> {p}")
    if result.get("duplicates"):
        lines.append(f"\n**Duplicates skipped:** {result['duplicates']}")
    if result["errors"]:
        lines.append(f"\n## Errors ({len(result['errors'])})")
        for err in result["errors"]:
            lines.append(f"  ! {err['source']}: {err['error']}")
    return "\n".join(lines)
