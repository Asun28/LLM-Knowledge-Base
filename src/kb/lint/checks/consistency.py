"""Cross-file consistency lint checks."""

import logging
from pathlib import Path

import frontmatter
import yaml

from kb.config import SUPPORTED_SOURCE_EXTENSIONS
from kb.lint import checks
from kb.utils.markdown import extract_raw_refs
from kb.utils.pages import normalize_sources, scan_wiki_pages
from kb.utils.paths import make_source_ref

logger = logging.getLogger(__name__)


def check_source_coverage(
    wiki_dir: Path | None = None,
    raw_dir: Path | None = None,
    pages: list[Path] | None = None,
) -> list[dict]:
    """Find raw sources not referenced in any wiki page.

    Returns:
        List of dicts: {source, message}.
    """
    wiki_dir = wiki_dir or checks.WIKI_DIR
    raw_dir = raw_dir or checks.RAW_DIR
    if pages is None:
        pages = scan_wiki_pages(wiki_dir)

    # Collect all raw references across wiki pages (single pass per file).
    # O1 (Phase 4.5 R4 HIGH): short-circuit pages missing the opening
    # frontmatter fence. `frontmatter.loads` returns empty metadata on these,
    # silently dropping any already-written `source:` YAML — producing
    # false-positive "Raw source not referenced" warnings. Flag the page as
    # malformed so the operator sees the actual problem.
    issues: list[dict] = []
    all_raw_refs = set()
    for page_path in pages:
        try:
            content = page_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("Failed to read page %s: %s", page_path, e)
            continue
        # Short-circuit: if the page has body-level raw refs but no frontmatter
        # fence, emit a frontmatter issue and skip the YAML parse (which would
        # silently return empty metadata).
        if not content.lstrip().startswith("---"):
            # PR review round 1: use "check" key so `runner.py` and downstream
            # consumers filtering by `i["check"]` surface this class (was "type").
            issues.append(
                {
                    "check": "frontmatter_missing_fence",
                    "severity": "warning",
                    "page": str(page_path.relative_to(wiki_dir))
                    if page_path.is_relative_to(wiki_dir)
                    else str(page_path),
                    "message": f"Missing opening frontmatter fence in {page_path.name}",
                }
            )
            # Still collect body-level refs so a malformed page's mentions
            # don't falsely flag their raw sources as orphans.
            refs = extract_raw_refs(content)
            all_raw_refs.update(refs)
            continue
        try:
            post = frontmatter.loads(content)
            all_raw_refs.update(normalize_sources(post.metadata.get("source")))
            all_raw_refs.update(extract_raw_refs(post.content))
        except (ValueError, AttributeError, yaml.YAMLError) as e:
            logger.warning("Failed to parse frontmatter for %s: %s", page_path, e)
            all_raw_refs.update(extract_raw_refs(content))

    # Find raw sources not referenced (append to issues collected above).
    for _type_name, type_dir in checks.SOURCE_TYPE_DIRS.items():
        actual_dir = raw_dir / type_dir.name
        if not actual_dir.exists():
            continue
        for f in actual_dir.rglob("*"):
            if (
                f.is_file()
                and f.name != ".gitkeep"
                and f.suffix.lower() in SUPPORTED_SOURCE_EXTENSIONS
            ):
                try:
                    rel_path = make_source_ref(f, raw_dir)
                except ValueError:
                    logger.warning("Skipping source outside raw_dir: %s", f)
                    continue
                # Check if this source is referenced (exact path only — no suffix match to avoid
                # false-positives when two subdirs contain same-named files)
                referenced = rel_path in all_raw_refs
                if not referenced:
                    issues.append(
                        {
                            "check": "source_coverage",
                            "severity": "warning",
                            "source": rel_path,
                            "message": f"Raw source not referenced in wiki: {rel_path}",
                        }
                    )

    return issues
