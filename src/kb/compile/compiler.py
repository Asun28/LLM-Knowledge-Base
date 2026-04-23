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
    WIKI_DIR,
)
from kb.errors import ValidationError
from kb.ingest.pipeline import ingest_source
from kb.utils.hashing import content_hash
from kb.utils.io import file_lock
from kb.utils.wiki_log import append_wiki_log

logger = logging.getLogger(__name__)

# Hash manifest location (git-ignored)
HASH_MANIFEST = PROJECT_ROOT / ".data" / "hashes.json"


def _template_hashes() -> dict[str, str]:
    """Compute content hashes for all extraction templates.

    Cycle 4 item #25 — filter by ``VALID_SOURCE_TYPES`` instead of just
    excluding editor dotfiles/tildes. Prevents stray files like
    ``article.yaml.bak`` (editor backup) from entering the manifest and
    forcing a full re-ingest when they change.
    """
    from kb.config import VALID_SOURCE_TYPES

    hashes = {}
    if not TEMPLATES_DIR.exists():
        return hashes
    for tpl in sorted(TEMPLATES_DIR.glob("*.yaml")):
        if tpl.stem.startswith(("~", ".")):
            continue
        if tpl.stem not in VALID_SOURCE_TYPES:
            continue
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


# Cycle 19 AC11 — public alias for the canonical manifest-key computation.
# Naming convention matches `decay_days_for` / `tier1_budget_for` / etc.
# Callers that need a canonical manifest key (e.g. `compile_wiki` threading
# through `ingest_source(manifest_key=...)`) should import this name; the
# underscored helper remains the implementation but is no longer the public
# API. NOT exposed in `kb.__all__` — internal to compile/ingest plumbing.
manifest_key_for = _canonical_rel_path


def load_manifest(manifest_path: Path | None = None) -> dict[str, str]:
    """Load the content hash manifest (source path → hash mapping).

    Returns:
        dict mapping relative source paths to their last-compiled content hashes.
    """
    manifest_path = manifest_path or HASH_MANIFEST
    if manifest_path.exists():
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
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

    Cycle 17 T2 same-class peer — when ``save_hashes=True`` the
    ``load_manifest → prune → save_manifest`` block below is the manifest RMW
    pair that AC3 covers for ``compile_wiki``'s tail. It is wrapped in
    ``file_lock(manifest_path)`` at the save site to preserve the same
    concurrent-writer invariant at every manifest RMW. The ``save_hashes=False``
    branch is read-only and does not need the lock.
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

    # Prune manifest entries for files that no longer exist on disk.
    # Cycle 25 CONDITION 13 — exempt `in_progress:`-valued entries so they
    # survive incremental compiles and AC7's startup scan can surface them.
    # Otherwise the default `kb compile` path silently deletes the markers
    # that the design contract says operators should see. (This mirrors the
    # exemption in compile_wiki's full-mode tail prune at line ~494.)
    deleted_keys = [
        k
        for k, v in manifest.items()
        if not k.startswith("_template/")
        and not str(v).startswith("in_progress:")
        and k not in existing_rel_paths
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
            if source_type not in SOURCE_TYPE_DIRS:
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
        # Cycle 17 T2 same-class peer — manifest RMW must hold file_lock so a
        # concurrent kb_ingest between our load_manifest (above) and save does
        # not lose its entry. Re-reading under the lock closes the RMW window.
        with file_lock(manifest_path):
            latest_manifest = load_manifest(manifest_path)
            # Re-apply our pruning + template updates on the freshly-loaded
            # manifest so we do not clobber concurrent writes.
            for k in deleted_keys:
                latest_manifest.pop(k, None)
            latest_manifest.update(current_tpl_hashes)
            save_manifest(latest_manifest, manifest_path)
    # Cycle 4 PR R1 Codex MAJOR 3 — previously `elif deleted_keys: save_manifest(...)`
    # ran even when save_hashes=False, which made detect_source_drift (the
    # documented read-only caller) mutate the manifest. The side effect caused
    # deleted sources to be reported ONCE then vanish on subsequent drift
    # checks. Drop the persistence entirely when save_hashes=False — the
    # compile loop (save_hashes=True) writes the pruned state at its normal
    # cadence, so deleted entries get cleaned up during the next compile,
    # not during a drift inspection.

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

    deletion-pruning of manifest entries is always persisted even when
    save_hashes=False is passed to find_changed_sources, because lingering
    deleted-source entries would corrupt subsequent find_changed_sources
    calls. This is the single exception to the read-only contract; callers
    should NOT assume detect_source_drift is side-effect-free on the
    manifest when raw sources have been deleted.
    """
    import frontmatter as fm

    from kb.config import WIKI_DIR as DEFAULT_WIKI_DIR
    from kb.utils.pages import normalize_sources, scan_wiki_pages
    from kb.utils.pages import page_id as get_page_id

    raw_dir = raw_dir or RAW_DIR
    wiki_dir = wiki_dir or DEFAULT_WIKI_DIR

    # Cycle 4 item #14 — capture deleted-source keys BEFORE find_changed_sources
    # runs its internal prune. These are the manifest entries whose backing
    # raw file no longer exists on disk — the drift case most likely to
    # corrupt lint fidelity (wiki pages still reference the deleted source).
    pre_prune_manifest = load_manifest(manifest_path)
    current_sources = scan_raw_sources(raw_dir)
    existing_rel = {_canonical_rel_path(s, raw_dir) for s in current_sources}
    deleted_refs = sorted(
        k for k in pre_prune_manifest if not k.startswith("_template/") and k not in existing_rel
    )

    new_sources, changed_sources = find_changed_sources(raw_dir, manifest_path, save_hashes=False)
    all_changed = new_sources + changed_sources

    if not all_changed and not deleted_refs:
        return {
            "changed_sources": [],
            "affected_pages": [],
            "deleted_sources": [],
            "deleted_affected_pages": [],
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

    # Cycle 4 item #14 — also compute pages whose source frontmatter points
    # at a now-deleted raw file (the "source-deleted" category).
    deleted_affected_pages: list[dict] = []
    if deleted_refs:
        deleted_ref_set = set(deleted_refs)
        wiki_pages = scan_wiki_pages(wiki_dir)
        for page_path in wiki_pages:
            try:
                post = fm.load(str(page_path))
                page_sources = normalize_sources(post.metadata.get("source"))
                deleted_matching = [s for s in page_sources if s in deleted_ref_set]
                if deleted_matching:
                    pid = get_page_id(page_path, wiki_dir)
                    deleted_affected_pages.append(
                        {
                            "page_id": pid,
                            "deleted_sources": deleted_matching,
                        }
                    )
            except (OSError, ValueError, AttributeError, yaml.YAMLError, UnicodeDecodeError):
                continue

    summary_parts = [
        f"{len(new_sources)} new source(s), {len(changed_sources)} changed source(s).",
    ]
    if deleted_refs:
        summary_parts.append(f"{len(deleted_refs)} source(s) deleted from raw/.")
    if affected_pages:
        summary_parts.append(f"{len(affected_pages)} wiki page(s) may need re-review.")
    elif not deleted_refs:
        summary_parts.append("No existing wiki pages reference the changed sources.")
    if deleted_affected_pages:
        summary_parts.append(
            f"{len(deleted_affected_pages)} wiki page(s) reference deleted source(s)."
        )

    return {
        "changed_sources": [_canonical_rel_path(s, raw_dir) for s in all_changed],
        "affected_pages": affected_pages,
        "deleted_sources": deleted_refs,
        "deleted_affected_pages": deleted_affected_pages,
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

    Note (cycle 23 AC1) — ``incremental=False`` does NOT invalidate these derived stores:

    - the hash manifest deletion-prune — runs only via ``detect_source_drift``;
      ``--full`` does not remove hashes for raw sources that were deleted since
      the last compile.
    - the vector index — embeddings are rebuilt incrementally inside
      ``ingest_source``; ``--full`` does not wipe and rebuild the whole index.
    - in-process LRU caches (template schemas, page frontmatter,
      ``wiki/purpose.md``) — they are not cleared by ``--full`` either.

    To wipe those derived stores, call ``rebuild_indexes(wiki_dir=...)``
    below, or invoke ``kb rebuild-indexes`` from the CLI before a clean
    full recompile.
    """
    raw_dir = raw_dir or RAW_DIR
    manifest_path = manifest_path or HASH_MANIFEST

    # Cycle 25 AC7 — scan for stale `in_progress:` markers from a prior
    # abortive run (hard-kill, power-loss between AC6's pre-marker write and
    # the subsequent ingest_source manifest overwrite). Log-only per Q2
    # (operator decides remediation; auto-delete would race a legitimate
    # concurrent compile per Q10). Truncation dropped per Step-8 plan-gate:
    # each stale source named individually so operators correlate with the
    # specific failed ingest.
    try:
        _existing_manifest_snapshot = load_manifest(manifest_path)
    except Exception as e:  # pragma: no cover — defensive
        logger.warning("compile_wiki: could not scan for stale markers: %s", e)
        _existing_manifest_snapshot = {}
    _stale_in_progress = [
        k for k, v in _existing_manifest_snapshot.items() if str(v).startswith("in_progress:")
    ]
    if _stale_in_progress:
        logger.warning(
            "compile_wiki: found %d stale in_progress marker(s) from a prior "
            "abortive run. Sources: %s. Investigate or run `kb rebuild-indexes` "
            "to clear. Concurrent in-flight compiles from another process may "
            "also produce this warning (see CLAUDE.md for details).",
            len(_stale_in_progress),
            ", ".join(_stale_in_progress),
        )

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

    processed_count = 0
    for source in sources_to_process:
        # Capture rel_path and hash BEFORE the try block so that if content_hash
        # raises, the except block can still record the failure without re-calling
        # content_hash (which would re-raise the same error).
        rel_path = _canonical_rel_path(source, raw_dir)
        try:
            pre_hash = content_hash(source)
        except OSError as e:
            logger.warning("compile_wiki: cannot hash %s, skipping: %s", source, e)
            results["errors"].append({"source": str(source), "error": str(e)})
            continue

        # Cycle 25 AC6 — write an in_progress marker AFTER pre_hash succeeds
        # and BEFORE the try block (Q5 placement). A hard-kill / power-loss
        # between this write and ingest_source's own manifest overwrite leaves
        # an `in_progress:{pre_hash}` row that AC7's entry scan surfaces on
        # the next compile_wiki invocation. Normal Python exceptions are
        # handled by the existing `except Exception` block below which
        # overwrites the marker with `failed:{pre_hash}`. Q4: 1.0s lock
        # timeout matches the cycle-23 rebuild_indexes convention.
        try:
            with file_lock(manifest_path, timeout=1.0):
                _marker_manifest = load_manifest(manifest_path)
                _marker_manifest[rel_path] = f"in_progress:{pre_hash}"
                save_manifest(_marker_manifest, manifest_path)
        except (TimeoutError, OSError) as marker_exc:
            # Best-effort: if the marker write fails, log and proceed.
            # ingest_source's own manifest write still provides normal
            # success/failure state tracking for this source.
            logger.warning(
                "compile_wiki: in_progress marker write failed for %s: %s",
                source,
                marker_exc,
            )

        try:
            # H17 fix: suppress per-source rebuild; one rebuild happens at loop tail.
            # Cycle 19 AC13 — thread the canonical rel_path as the explicit
            # manifest_key so ingest_source's reservation + tail confirmation
            # both use the SAME key (closes the dual-write divergence class
            # under non-default raw_dir / Windows case differences).
            ingest_result = ingest_source(
                source,
                wiki_dir=wiki_dir,
                manifest_key=rel_path,
                _skip_vector_rebuild=True,
            )
            results["sources_processed"] += 1
            results["pages_created"].extend(ingest_result["pages_created"])
            results["pages_updated"].extend(ingest_result["pages_updated"])
            results["pages_skipped"].extend(ingest_result.get("pages_skipped", []))
            results["wikilinks_injected"].extend(ingest_result.get("wikilinks_injected", []))
            results["affected_pages"].extend(ingest_result.get("affected_pages", []))
            if ingest_result.get("duplicate"):
                results["duplicates"] += 1

            processed_count += 1
        except Exception as e:
            logger.exception("compile_wiki: ingest failed for %s", source)
            results["errors"].append({"source": str(source), "error": str(e)})
            # Cycle 17 AC3 — exception-path manifest RMW must hold file_lock so
            # a concurrent kb_ingest that updates the manifest in this window
            # cannot be clobbered by our load → update → save sequence.
            # pre_hash is already captured above; no need to re-call content_hash.
            try:
                with file_lock(manifest_path):
                    manifest = load_manifest(manifest_path)
                    manifest[rel_path] = f"failed:{pre_hash}"
                    save_manifest(manifest, manifest_path)
            except Exception as inner_exc:
                logger.warning("Failed to record failed hash for %s: %s", source, inner_exc)

    # Save template hashes only in full mode.
    # In incremental mode, find_changed_sources already wrote template hashes and
    # ingest_source already persisted per-source hashes — no additional save needed.
    if not incremental:
        # Cycle 17 AC3 — wrap full-mode tail reload+prune+save in file_lock so
        # a concurrent kb_ingest between our load_manifest and save_manifest does
        # not lose its entry. Matches the per-source lock convention used by the
        # ingest pipeline (manifest_path is the last lock in the documented order).
        # Cycle 17 AC1 — prune base uses raw_dir.resolve().parent to match
        # _canonical_rel_path's base under relative / symlinked / dotted raw_dir
        # inputs; raw_dir.parent alone produces cwd-relative semantics that can
        # diverge from the canonical key base.
        prune_base = raw_dir.resolve().parent
        with file_lock(manifest_path):
            current_manifest = load_manifest(manifest_path)
            current_manifest.update(_template_hashes())
            # Prune manifest entries for sources that no longer exist on disk.
            # Cycle 25 CONDITION 13 — EXEMPT `in_progress:`-valued entries
            # from pruning so AC7's "operator decides remediation" contract
            # holds: full-mode compile must NOT silently delete the markers
            # that AC7 says operators should see.
            stale_keys = [
                k
                for k, v in current_manifest.items()
                if not k.startswith("_template/")
                and not str(v).startswith("in_progress:")
                and not (prune_base / k).exists()
            ]
            if stale_keys:
                for k in stale_keys:
                    del current_manifest[k]
                logger.info("Pruned %d stale manifest entries in full mode", len(stale_keys))
            save_manifest(current_manifest, manifest_path)

    # H17 fix: single vector index rebuild after all sources are processed.
    # Per-source ingest_source calls used _skip_vector_rebuild=True to avoid
    # N redundant rebuilds during a compile run.
    effective_wiki_dir = wiki_dir if wiki_dir is not None else WIKI_DIR
    try:
        from kb.query.embeddings import rebuild_vector_index

        rebuild_vector_index(effective_wiki_dir)
    except Exception as e:
        logger.warning("Final vector index rebuild at compile tail failed: %s", e)

    # Append to log — use effective_wiki_dir if provided, else fall back to global WIKI_DIR.
    effective_log_dir = effective_wiki_dir
    append_wiki_log(
        "compile",
        f"{results['mode']} compile: {results['sources_processed']} sources, "
        f"{len(results['pages_created'])} pages created, "
        f"{len(results['pages_updated'])} pages updated, "
        f"{len(results['pages_skipped'])} skipped, "
        f"{results['duplicates']} duplicate(s), "
        f"{len(results['errors'])} errors",
        effective_log_dir / "log.md",
    )

    return results


def rebuild_indexes(
    wiki_dir: Path | None = None,
    *,
    hash_manifest: Path | None = None,
    vector_db: Path | None = None,
) -> dict:
    """Wipe derived indices so the next compile/query regenerates from source.

    Clears, in order:

    1. the **hash manifest** (``HASH_MANIFEST`` by default) — taken under
       ``file_lock`` with a 1s wait, so a concurrent ``compile_wiki`` save
       cannot racing-rewrite stale state after we unlink. On
       ``TimeoutError`` the manifest is left in place and ``error='lock busy'``
       is returned; rerun the operation once the in-flight compile finishes.
    2. the **vector index DB** (``<wiki_dir>.parent/.data/vector_index.db``
       by default, derived via ``kb.query.embeddings._vec_db_path``).
       Embeddings rebuild on the next query/compile.
    3. in-process **LRU caches** — ``kb.ingest.extractors.clear_template_cache``
       (covering ``_load_template_cached`` + ``_build_schema_cached``), plus
       ``kb.utils.pages._load_page_frontmatter_cached`` and
       ``kb.utils.pages.load_purpose``. Each cleared helper is named in
       the returned ``caches_cleared`` list.

    Appends one ``rebuild-indexes`` line to ``<wiki_dir>/log.md`` after the
    file operations so a failed audit cannot silently obscure the fact
    that destructive work ran (audit-write failures log a warning and
    surface via ``audit_written=False`` — they never swallow the whole
    rebuild).

    Args:
        wiki_dir: Target wiki directory. Defaults to ``WIKI_DIR``. Must
                  resolve under ``PROJECT_ROOT`` (cycle 23 threat I1).
        hash_manifest: Override manifest path. Defaults to
                       ``HASH_MANIFEST``.
        vector_db: Override vector DB path. Defaults to
                   ``_vec_db_path(wiki_dir)``.

    Returns:
        ``{"manifest": {"cleared": bool, "error": str | None},
           "vector": {"cleared": bool, "error": str | None},
           "caches_cleared": list[str],
           "audit_written": bool}``

    Raises:
        ``ValidationError`` — ``wiki_dir`` does not resolve under ``PROJECT_ROOT``.
    """
    effective_wiki = Path(wiki_dir).expanduser() if wiki_dir else WIKI_DIR
    root_resolved = PROJECT_ROOT.resolve()
    # Cycle 23 Q5 / threat I1 — DUAL-anchor containment. Check the caller-
    # supplied absolute path AND the resolved path both land under
    # PROJECT_ROOT. This closes the symlink escape where
    # ``/outside/link -> /proj/wiki`` would slip through a resolve()-only
    # check (post-resolve looks clean even though the CALLER aimed at
    # `/outside`). Relative inputs skip the pre-check because ``resolve()``
    # absolutifies against CWD, which may legitimately differ from project
    # root in dev workflows.
    if effective_wiki.is_absolute() and not (
        effective_wiki == root_resolved or effective_wiki.is_relative_to(root_resolved)
    ):
        raise ValidationError("wiki_dir must be inside project root")
    try:
        wiki_resolved = effective_wiki.resolve()
    except OSError as e:
        raise ValidationError(f"wiki_dir cannot be resolved: {e}") from e
    if not (wiki_resolved == root_resolved or wiki_resolved.is_relative_to(root_resolved)):
        raise ValidationError("wiki_dir must be inside project root")

    manifest_path = hash_manifest or HASH_MANIFEST
    from kb.query.embeddings import _vec_db_path

    vector_path = vector_db or _vec_db_path(effective_wiki)

    result: dict = {
        "manifest": {"cleared": False, "error": None},
        "vector": {"cleared": False, "error": None},
        "caches_cleared": [],
        "audit_written": False,
    }

    # (1) Manifest — unlink under file_lock so a concurrent compile_wiki
    # save cannot race us.
    try:
        with file_lock(manifest_path, timeout=1.0):
            if manifest_path.exists():
                manifest_path.unlink()
            result["manifest"]["cleared"] = True
    except TimeoutError:
        result["manifest"]["error"] = "lock busy"
    except OSError as e:
        result["manifest"]["error"] = str(e)

    # (2) Vector DB — single-writer contract inside embeddings.py, unlocked
    # unlink is sufficient.  Symlinks are not followed: Path.unlink removes
    # the symlink itself, the target survives by design.
    vec_error: str | None = None
    tmp_error: str | None = None
    try:
        if vector_path.exists():
            vector_path.unlink()
        result["vector"]["cleared"] = True
    except OSError as e:
        vec_error = str(e)

    # Cycle 25 AC1 — also unlink the <vec_db>.tmp sibling produced by
    # rebuild_vector_index's atomic tmp-then-replace flow (cycle 24 AC5). If
    # a prior rebuild crashed, a stale `.tmp` survives alongside the main DB
    # until the next rebuild's AC6 entry-cleanup. Extending rebuild_indexes
    # to clean it up gives operators a single-command full reset.
    #
    # Q9 resolution: derive tmp from the effective `vector_path` (which
    # already honours the optional `vector_db=` override), NOT from
    # `_vec_db_path(effective_wiki)` — otherwise a caller using the override
    # would see its sibling `.tmp` retained.
    #
    # Q1 / CONDITION 1: a tmp-unlink failure MUST NOT blank the main
    # `cleared=True` status when the main unlink succeeded; errors are
    # reported via the compound error message below.
    tmp_path = vector_path.parent / (vector_path.name + ".tmp")
    try:
        tmp_path.unlink(missing_ok=True)
    except OSError as e:
        tmp_error = str(e)

    # Surface compound error covering both paths when either failed. The
    # `cleared` flag reflects the MAIN vector DB's state; tmp cleanup is
    # hygiene and does not downgrade a successful main unlink.
    if vec_error or tmp_error:
        parts: list[str] = []
        if vec_error:
            parts.append(f"vec: {vec_error}")
        if tmp_error:
            parts.append(f"tmp: {tmp_error}")
        result["vector"]["error"] = "; ".join(parts)

    # (3) LRU caches — clear every mtime- or path-keyed cache that could
    # otherwise serve pre-rebuild metadata after a subsequent ingest.
    try:
        from kb.ingest.extractors import clear_template_cache

        clear_template_cache()
        result["caches_cleared"].append("kb.ingest.extractors.clear_template_cache")
    except Exception as e:  # pragma: no cover — defensive against future refactors
        logger.warning("rebuild_indexes: clear_template_cache failed: %s", e)
    try:
        from kb.utils.pages import _load_page_frontmatter_cached

        _load_page_frontmatter_cached.cache_clear()
        result["caches_cleared"].append("kb.utils.pages._load_page_frontmatter_cached")
    except (AttributeError, ImportError) as e:
        logger.warning("rebuild_indexes: _load_page_frontmatter_cached clear failed: %s", e)
    try:
        from kb.utils.pages import load_purpose

        load_purpose.cache_clear()
        result["caches_cleared"].append("kb.utils.pages.load_purpose")
    except (AttributeError, ImportError) as e:
        logger.warning("rebuild_indexes: load_purpose clear failed: %s", e)

    # (4) Audit — append one line to wiki/log.md. Best-effort; failure does
    # not abort the helper because the unlinks already happened.
    log_path = effective_wiki / "log.md"
    msg = (
        f"manifest={'cleared' if result['manifest']['cleared'] else result['manifest']['error']} "
        f"vector={'cleared' if result['vector']['cleared'] else result['vector']['error']} "
        f"caches_cleared={len(result['caches_cleared'])}"
    )
    try:
        append_wiki_log("rebuild-indexes", msg, log_path)
        result["audit_written"] = True
    except OSError as e:
        logger.warning("rebuild_indexes: audit write to %s failed: %s", log_path, e)

    return result
