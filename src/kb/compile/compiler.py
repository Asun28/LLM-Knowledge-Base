"""Compile orchestrator — build/update wiki pages from raw sources."""

import json
from pathlib import Path

from kb.config import PROJECT_ROOT, RAW_DIR, SOURCE_TYPE_DIRS, WIKI_LOG
from kb.ingest.pipeline import ingest_source
from kb.utils.hashing import content_hash

# Hash manifest location (git-ignored)
HASH_MANIFEST = PROJECT_ROOT / ".data" / "hashes.json"


def load_manifest(manifest_path: Path | None = None) -> dict[str, str]:
    """Load the content hash manifest (source path → hash mapping).

    Returns:
        dict mapping relative source paths to their last-compiled content hashes.
    """
    manifest_path = manifest_path or HASH_MANIFEST
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    return {}


def save_manifest(manifest: dict[str, str], manifest_path: Path | None = None) -> None:
    """Save the content hash manifest."""
    manifest_path = manifest_path or HASH_MANIFEST
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


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
        rel_path = str(source).replace("\\", "/")
        current_hash = content_hash(source)

        if rel_path not in manifest:
            new_sources.append(source)
        elif manifest[rel_path] != current_hash:
            changed_sources.append(source)

    return new_sources, changed_sources


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
        "errors": [],
    }

    for source in sources_to_process:
        try:
            ingest_result = ingest_source(source)
            results["sources_processed"] += 1
            results["pages_created"].extend(ingest_result["pages_created"])
            results["pages_updated"].extend(ingest_result["pages_updated"])

            # Update manifest with new hash
            rel_path = str(source).replace("\\", "/")
            manifest[rel_path] = content_hash(source)
        except Exception as e:
            results["errors"].append({"source": str(source), "error": str(e)})

    # Save updated manifest
    save_manifest(manifest, manifest_path)

    # Append to log
    _append_compile_log(results)

    return results


def _append_compile_log(results: dict) -> None:
    """Append compile results to wiki/log.md."""
    from datetime import date

    entry = (
        f"- {date.today().isoformat()} | compile | "
        f"{results['mode']} compile: {results['sources_processed']} sources, "
        f"{len(results['pages_created'])} pages created, "
        f"{len(results['pages_updated'])} pages updated, "
        f"{len(results['errors'])} errors\n"
    )
    if WIKI_LOG.exists():
        content = WIKI_LOG.read_text(encoding="utf-8")
        content += entry
        WIKI_LOG.write_text(content, encoding="utf-8")
