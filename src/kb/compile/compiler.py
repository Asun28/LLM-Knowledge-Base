"""Compile orchestrator — build/update wiki pages from raw sources."""

import json
import logging
from pathlib import Path

import yaml

from kb.config import PROJECT_ROOT, RAW_DIR, SOURCE_TYPE_DIRS, TEMPLATES_DIR
from kb.ingest.extractors import VALID_SOURCE_TYPES
from kb.ingest.pipeline import ingest_source
from kb.utils.hashing import content_hash
from kb.utils.wiki_log import append_wiki_log

logger = logging.getLogger(__name__)

# Hash manifest location (git-ignored)
HASH_MANIFEST = PROJECT_ROOT / ".data" / "hashes.json"


def _template_hashes() -> dict[str, str]:
    """Compute content hashes for all extraction templates."""
    hashes = {}
    if not TEMPLATES_DIR.exists():
        return hashes
    for tpl in sorted(TEMPLATES_DIR.glob("*.yaml")):
        hashes[f"_template/{tpl.stem}"] = content_hash(tpl)
    return hashes


def _canonical_rel_path(source: Path, raw_dir: Path) -> str:
    """Compute a canonical relative path for a source file (always forward slashes).

    Uses raw_dir's parent (project root) as the base, producing paths like
    'raw/articles/example.md' regardless of OS.
    """
    try:
        return str(source.resolve().relative_to(raw_dir.resolve().parent)).replace("\\", "/")
    except ValueError:
        return str(source).replace("\\", "/")


def load_manifest(manifest_path: Path | None = None) -> dict[str, str]:
    """Load the content hash manifest (source path → hash mapping).

    Returns:
        dict mapping relative source paths to their last-compiled content hashes.
    """
    manifest_path = manifest_path or HASH_MANIFEST
    if manifest_path.exists():
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning("Corrupt manifest %s, resetting to empty: %s", manifest_path, e)
            return {}
    return {}


def save_manifest(manifest: dict[str, str], manifest_path: Path | None = None) -> None:
    """Save the content hash manifest (atomic write via temp file)."""
    from kb.utils.io import atomic_json_write

    manifest_path = manifest_path or HASH_MANIFEST
    atomic_json_write(manifest, manifest_path)


def scan_raw_sources(raw_dir: Path | None = None) -> list[Path]:
    """Find all source files in raw/ subdirectories.

    Skips .gitkeep files and the assets/ directory.
    """
    raw_dir = raw_dir or RAW_DIR
    sources = []
    for type_name, type_dir in SOURCE_TYPE_DIRS.items():
        # Use the actual directory under the given raw_dir
        actual_dir = raw_dir / type_dir.name
        if not actual_dir.exists():
            continue
        for f in sorted(actual_dir.iterdir()):
            if (
                f.is_file()
                and f.suffix in (".md", ".txt", ".pdf", ".json", ".yaml")
                and f.name != ".gitkeep"
            ):
                sources.append(f)
    return sources


def find_changed_sources(
    raw_dir: Path | None = None,
    manifest_path: Path | None = None,
) -> tuple[list[Path], list[Path]]:
    """Find new and changed source files by comparing content hashes.

    Args:
        raw_dir: Path to raw directory.
        manifest_path: Path to hash manifest file.

    Returns:
        Tuple of (new_sources, changed_sources).
    """
    manifest = load_manifest(manifest_path)
    all_sources = scan_raw_sources(raw_dir)

    new_sources = []
    changed_sources = []

    for source in all_sources:
        rel_path = _canonical_rel_path(source, raw_dir or RAW_DIR)
        current_hash = content_hash(source)

        if rel_path not in manifest:
            new_sources.append(source)
        elif manifest[rel_path] != current_hash:
            changed_sources.append(source)

    # Check for template changes — flag all sources of that type for recompilation
    current_tpl_hashes = _template_hashes()
    changed_source_set = {s.resolve() for s in new_sources + changed_sources}
    effective_raw_dir = raw_dir or RAW_DIR

    for key, current_hash in current_tpl_hashes.items():
        stored_hash = manifest.get(key)
        if stored_hash != current_hash:
            # Template changed — determine source type from key (_template/<type>)
            source_type = key.split("/", 1)[1]
            if source_type not in VALID_SOURCE_TYPES:
                continue
            type_dir = effective_raw_dir / SOURCE_TYPE_DIRS[source_type].name
            if not type_dir.exists():
                continue
            for f in sorted(type_dir.iterdir()):
                if (
                    f.is_file()
                    and f.suffix in (".md", ".txt", ".pdf", ".json", ".yaml")
                    and f.name != ".gitkeep"
                    and f.resolve() not in changed_source_set
                ):
                    changed_sources.append(f)
                    changed_source_set.add(f.resolve())

    # Update manifest with current template hashes
    manifest.update(current_tpl_hashes)
    save_manifest(manifest, manifest_path)

    return new_sources, changed_sources


def detect_source_drift(
    raw_dir: Path | None = None,
    wiki_dir: Path | None = None,
    manifest_path: Path | None = None,
) -> dict:
    """Detect wiki pages that may be stale due to raw source changes.

    Finds sources whose content has changed since last compile, then identifies
    which wiki pages reference those sources (via frontmatter source: field).

    Args:
        raw_dir: Path to raw directory.
        wiki_dir: Path to wiki directory.
        manifest_path: Path to hash manifest file.

    Returns:
        dict with keys: changed_sources, affected_pages, summary.
    """
    import frontmatter as fm

    from kb.config import WIKI_DIR as DEFAULT_WIKI_DIR
    from kb.graph.builder import page_id as get_page_id
    from kb.graph.builder import scan_wiki_pages
    from kb.utils.pages import normalize_sources

    raw_dir = raw_dir or RAW_DIR
    wiki_dir = wiki_dir or DEFAULT_WIKI_DIR

    new_sources, changed_sources = find_changed_sources(raw_dir, manifest_path)
    all_changed = new_sources + changed_sources

    if not all_changed:
        return {
            "changed_sources": [],
            "affected_pages": [],
            "summary": "No source changes detected. Wiki is up to date.",
        }

    # Build set of changed source refs (canonical paths)
    changed_refs = set()
    for source in all_changed:
        ref = _canonical_rel_path(source, raw_dir)
        changed_refs.add(ref)

    # Scan wiki pages to find which reference the changed sources
    affected_pages = []
    wiki_pages = scan_wiki_pages(wiki_dir)

    for page_path in wiki_pages:
        try:
            post = fm.load(str(page_path))
            page_sources = normalize_sources(post.metadata.get("source"))
            matching = [s for s in page_sources if s in changed_refs]
            if matching:
                pid = get_page_id(page_path, wiki_dir)
                affected_pages.append(
                    {
                        "page_id": pid,
                        "changed_sources": matching,
                    }
                )
        except (OSError, ValueError, AttributeError, yaml.YAMLError, UnicodeDecodeError):
            logger.warning("Skipping unreadable page %s during drift detection", page_path)
            continue

    summary_parts = [
        f"{len(new_sources)} new source(s), {len(changed_sources)} changed source(s).",
    ]
    if affected_pages:
        summary_parts.append(f"{len(affected_pages)} wiki page(s) may need re-review.")
    else:
        summary_parts.append("No existing wiki pages reference the changed sources.")

    return {
        "changed_sources": [_canonical_rel_path(s, raw_dir) for s in all_changed],
        "affected_pages": affected_pages,
        "summary": " ".join(summary_parts),
    }


def compile_wiki(
    incremental: bool = True,
    raw_dir: Path | None = None,
    manifest_path: Path | None = None,
) -> dict:
    """Compile wiki pages from raw sources.

    In incremental mode, only processes new and changed sources.
    In full mode, recompiles everything.

    Args:
        incremental: If True, only process changed sources. If False, recompile all.
        raw_dir: Path to raw directory.
        manifest_path: Path to hash manifest file.

    Returns:
        dict with keys: mode, sources_processed, pages_created, pages_updated, errors.
    """
    raw_dir = raw_dir or RAW_DIR
    manifest_path = manifest_path or HASH_MANIFEST
    manifest = load_manifest(manifest_path)

    if incremental:
        new_sources, changed_sources = find_changed_sources(raw_dir, manifest_path)
        sources_to_process = new_sources + changed_sources
    else:
        sources_to_process = scan_raw_sources(raw_dir)

    results = {
        "mode": "incremental" if incremental else "full",
        "sources_processed": 0,
        "pages_created": [],
        "pages_updated": [],
        "pages_skipped": [],
        "wikilinks_injected": [],
        "affected_pages": [],
        "duplicates": 0,
        "errors": [],
    }

    for source in sources_to_process:
        try:
            ingest_result = ingest_source(source)
            results["sources_processed"] += 1
            results["pages_created"].extend(ingest_result["pages_created"])
            results["pages_updated"].extend(ingest_result["pages_updated"])
            results["pages_skipped"].extend(ingest_result.get("pages_skipped", []))
            results["wikilinks_injected"].extend(ingest_result.get("wikilinks_injected", []))
            results["affected_pages"].extend(ingest_result.get("affected_pages", []))
            if ingest_result.get("duplicate"):
                results["duplicates"] += 1

            # Update manifest and save immediately (crash-safe)
            rel_path = _canonical_rel_path(source, raw_dir)
            manifest[rel_path] = content_hash(source)
            save_manifest(manifest, manifest_path)
        except Exception as e:
            results["errors"].append({"source": str(source), "error": str(e)})

    # Save template hashes
    manifest.update(_template_hashes())
    save_manifest(manifest, manifest_path)

    # Append to log
    append_wiki_log(
        "compile",
        f"{results['mode']} compile: {results['sources_processed']} sources, "
        f"{len(results['pages_created'])} pages created, "
        f"{len(results['pages_updated'])} pages updated, "
        f"{len(results['pages_skipped'])} skipped, "
        f"{results['duplicates']} duplicate(s), "
        f"{len(results['errors'])} errors",
    )

    return results
