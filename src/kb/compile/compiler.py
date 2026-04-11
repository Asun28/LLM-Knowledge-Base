"""Compile orchestrator — build/update wiki pages from raw sources."""

import json
import logging
from pathlib import Path

import yaml

from kb.config import (
    PROJECT_ROOT,
    RAW_DIR,
    SOURCE_TYPE_DIRS,
    SUPPORTED_SOURCE_EXTENSIONS,
    TEMPLATES_DIR,
)
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
        abs_path = str(source).replace("\\", "/")
        logger.warning(
            "Source %s is outside raw_dir parent; using absolute path as manifest key", abs_path
        )
        return abs_path


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
    Warns about unknown subdirectories that are not indexed by any source type.
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
                and f.suffix.lower() in SUPPORTED_SOURCE_EXTENSIONS
                and f.name != ".gitkeep"
            ):
                sources.append(f)

    # Warn about unknown subdirectories not covered by any source type
    known_dirs = {type_dir.name for type_dir in SOURCE_TYPE_DIRS.values()} | {"assets"}
    if raw_dir.exists():
        for subdir in raw_dir.iterdir():
            if (
                subdir.is_dir()
                and subdir.name not in known_dirs
                and not subdir.name.startswith(".")
            ):
                logger.warning(
                    "Unknown subdirectory in raw/: %s — not indexed by any source type",
                    subdir.name,
                )

    return sources


def find_changed_sources(
    raw_dir: Path | None = None,
    manifest_path: Path | None = None,
    save_hashes: bool = True,
) -> tuple[list[Path], list[Path]]:
    """Find new and changed source files by comparing content hashes.

    Args:
        raw_dir: Path to raw directory.
        manifest_path: Path to hash manifest file.
        save_hashes: If True (default), update the manifest with current template hashes.
            Pass False for read-only callers (e.g. detect_source_drift) to avoid wiping
            out the template hash diff before the next compile scan sees it.

    Returns:
        Tuple of (new_sources, changed_sources).
    """
    manifest = load_manifest(manifest_path)
    all_sources = scan_raw_sources(raw_dir)

    new_sources = []
    changed_sources = []

    # Build set of currently existing rel_paths so we can prune deleted entries
    existing_rel_paths: set[str] = set()

    for source in all_sources:
        rel_path = _canonical_rel_path(source, raw_dir or RAW_DIR)
        existing_rel_paths.add(rel_path)
        current_hash = content_hash(source)
        stored = manifest.get(rel_path)

        if stored is None:
            new_sources.append(source)
        elif stored.startswith("failed:") or stored != current_hash:
            changed_sources.append(source)

    # Prune manifest entries for files that no longer exist on disk
    deleted_keys = [
        k
        for k in list(manifest.keys())
        if not k.startswith("_template/") and k not in existing_rel_paths
    ]
    for k in deleted_keys:
        del manifest[k]

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
                    and f.suffix.lower() in SUPPORTED_SOURCE_EXTENSIONS
                    and f.name != ".gitkeep"
                    and f.resolve() not in changed_source_set
                ):
                    changed_sources.append(f)
                    changed_source_set.add(f.resolve())

    if save_hashes:
        # Update manifest with current template hashes and save (includes pruned entries)
        manifest.update(current_tpl_hashes)
        save_manifest(manifest, manifest_path)
    elif deleted_keys:
        # Even if not saving hashes, persist pruned manifest so deleted sources don't linger
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

    new_sources, changed_sources = find_changed_sources(raw_dir, manifest_path, save_hashes=False)
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
    wiki_dir: Path | None = None,
) -> dict:
    """Compile wiki pages from raw sources.

    In incremental mode, only processes new and changed sources.
    In full mode, recompiles everything.

    Args:
        incremental: If True, only process changed sources. If False, recompile all.
        raw_dir: Path to raw directory.
        manifest_path: Path to hash manifest file.
        wiki_dir: Path to wiki directory (forwarded to ingest_source).

    Returns:
        dict with keys: mode, sources_processed, pages_created, pages_updated, errors.
    """
    raw_dir = raw_dir or RAW_DIR
    manifest_path = manifest_path or HASH_MANIFEST

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
            # Capture hash BEFORE ingest_source (file may be modified by ingest tools)
            rel_path = _canonical_rel_path(source, raw_dir)
            pre_hash = content_hash(source)

            ingest_result = ingest_source(source, wiki_dir=wiki_dir)
            results["sources_processed"] += 1
            results["pages_created"].extend(ingest_result["pages_created"])
            results["pages_updated"].extend(ingest_result["pages_updated"])
            results["pages_skipped"].extend(ingest_result.get("pages_skipped", []))
            results["wikilinks_injected"].extend(ingest_result.get("wikilinks_injected", []))
            results["affected_pages"].extend(ingest_result.get("affected_pages", []))
            if ingest_result.get("duplicate"):
                results["duplicates"] += 1

            # Reload manifest from disk before overwriting — avoid clobbering concurrent writes
            manifest = load_manifest(manifest_path)
            # Store pre-ingest hash and save immediately (crash-safe)
            manifest[rel_path] = pre_hash
            save_manifest(manifest, manifest_path)
        except Exception as e:
            results["errors"].append({"source": str(source), "error": str(e)})
            # Record failed hash so the source is retried on next compile
            try:
                rel_path = _canonical_rel_path(source, raw_dir)
                pre_hash = content_hash(source)
                manifest = load_manifest(manifest_path)
                manifest[rel_path] = f"failed:{pre_hash}"
                save_manifest(manifest, manifest_path)
            except Exception as inner_exc:
                logger.warning("Failed to record failed hash for %s: %s", source, inner_exc)

    # Save template hashes (reload manifest first to preserve per-source hashes
    # written during the loop, then merge template hashes).
    # In incremental mode, find_changed_sources already wrote template hashes;
    # only recompute them in full mode where find_changed_sources was not called.
    current_manifest = load_manifest(manifest_path)
    if not incremental:
        current_manifest.update(_template_hashes())
        # Prune manifest entries for sources that no longer exist on disk
        existing_refs = {_canonical_rel_path(s, raw_dir) for s in sources_to_process}
        stale_keys = [
            k for k in current_manifest
            if not k.startswith("_template/") and k not in existing_refs
        ]
        if stale_keys:
            for k in stale_keys:
                del current_manifest[k]
            logger.info("Pruned %d stale manifest entries in full mode", len(stale_keys))
    save_manifest(current_manifest, manifest_path)

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
