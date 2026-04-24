"""CLI entry point for knowledge base operations.

Exit-code contract (Cycle 7 AC16):
    0 — success (including lint runs whose only issues are warnings).
    1 — error (explicit failure, uncaught exception, or lint hard error).

Cycle 7 AC30 — ``kb --version`` short-circuits BEFORE ``kb.config`` is
imported so version queries never fail when the operator's config/env is
broken. Do not move imports above the guard.
"""

import sys

# AC30: version short-circuit must run before any ``kb.config`` import.
if len(sys.argv) == 2 and sys.argv[1] in {"--version", "-V"}:
    from kb import __version__ as _kb_version

    sys.stdout.write(f"kb, version {_kb_version}\n")
    sys.exit(0)

import logging  # noqa: E402
import os  # noqa: E402
import traceback  # noqa: E402
from pathlib import Path  # noqa: E402

import click  # noqa: E402

from kb import __version__  # noqa: E402
from kb.config import SOURCE_TYPE_DIRS  # noqa: E402
from kb.utils.io import sweep_orphan_tmp  # noqa: E402
from kb.utils.text import truncate as _truncate_text  # noqa: E402


def _truncate(msg: str, limit: int = 600) -> str:
    """Truncate long error messages to avoid terminal flooding.

    Cycle 3 M17: delegate to `kb.utils.text.truncate` so CLI errors use the
    same head+tail smart-truncate as every other error surface. Default
    limit raised from 500 to 600 to match the utils helper.
    """
    return _truncate_text(msg, limit=limit)


def _is_debug_mode() -> bool:
    """Cycle 6 AC9 — return True if traceback should be printed to stderr.

    Sources: ``--verbose`` / ``-v`` flag stored on the Click context object,
    OR ``KB_DEBUG=1`` env var. Default (no env, no flag) preserves the
    existing user-facing truncated error-line behavior.
    """
    try:
        ctx = click.get_current_context(silent=True)
    except RuntimeError:
        ctx = None
    if ctx is not None and isinstance(ctx.obj, dict) and ctx.obj.get("verbose"):
        return True
    return os.environ.get("KB_DEBUG", "").strip() in {"1", "true", "yes", "on"}


def _error_exit(exc: BaseException, *, code: int = 1) -> None:
    """Standard CLI error exit. Prints truncated message, traceback if debug.

    Cycle 6 AC9: when ``KB_DEBUG=1`` or ``--verbose`` is set, prints the full
    ``traceback.format_exc()`` to stderr BEFORE the user-facing ``Error:``
    line so operators can diagnose transient failures without re-running.
    """
    if _is_debug_mode():
        click.echo(traceback.format_exc(), err=True)
    click.echo(f"Error: {_truncate(str(exc))}", err=True)
    sys.exit(code)


def _setup_logging() -> None:
    """Idempotent logging setup. Exposed so direct callers (tests, alt entry
    points) can configure logging without going through Click's context
    machinery. Cycle 6 factors this out so the legacy
    ``cli_module.cli.callback()`` test path keeps working despite the new
    `@click.pass_context` decorator.
    """
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")


@click.group()
@click.version_option(__version__)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Print full tracebacks on error (same as KB_DEBUG=1).",
)
@click.pass_context
def cli(ctx: click.Context | None = None, verbose: bool = False):
    """LLM Knowledge Base — compile raw sources into a structured wiki."""
    if ctx is not None:
        ctx.ensure_object(dict)
        ctx.obj["verbose"] = verbose
    _setup_logging()
    # Cycle 13 AC7: sweep orphan atomic-write .tmp siblings from hot dirs.
    # Runs after the AC30 --version short-circuit (line 15-19) and after
    # Click's eager --version/--help callbacks (which exit before the group
    # body runs). Helper is no-op on missing dirs, swallows all errors at
    # WARNING, never raises. Dedup resolved paths so a pathological config
    # where .data alias-resolves to WIKI_DIR sweeps once, not twice.
    #
    # Cycle 13 R1 fix: each ``Path.resolve()`` is wrapped because a broken
    # symlink, symlink loop, or inaccessible mount can raise OSError /
    # RuntimeError BEFORE the helper's own swallowing kicks in. AC7 contract
    # forbids the sweep from blocking CLI boot; failed-resolve targets are
    # logged WARNING and skipped (helper has the same behaviour).
    from kb.config import PROJECT_ROOT, WIKI_DIR

    sweep_targets: set[Path] = set()
    for raw_target in (PROJECT_ROOT / ".data", WIKI_DIR):
        try:
            sweep_targets.add(Path(raw_target).resolve())
        except (OSError, RuntimeError) as exc:  # broken symlink / loop / EACCES
            logging.getLogger(__name__).warning(
                "kb CLI sweep: skipping unresolvable target %s (%s)",
                raw_target,
                exc,
            )
    for target in sorted(sweep_targets):
        sweep_orphan_tmp(target)


@cli.command()
@click.argument("source_path")
@click.option(
    "--type",
    "source_type",
    type=click.Choice(sorted(SOURCE_TYPE_DIRS.keys())),
    help="Source type (auto-detected if omitted)",
)
def ingest(source_path: str, source_type: str | None):
    """Ingest a raw source into the knowledge base."""
    from kb.ingest.pipeline import ingest_source

    source = Path(source_path).resolve()
    click.echo(f"Ingesting: {source}")
    try:
        result = ingest_source(source, source_type)
        if result.get("duplicate"):
            click.echo(f"  Duplicate skipped (hash: {result['content_hash']})")
            return
        click.echo(f"  Type: {result['source_type']}")
        click.echo(f"  Hash: {result['content_hash']}")
        click.echo(f"  Pages created: {len(result['pages_created'])}")
        for page in result["pages_created"]:
            click.echo(f"    + {page}")
        click.echo(f"  Pages updated: {len(result['pages_updated'])}")
        for page in result["pages_updated"]:
            click.echo(f"    ~ {page}")
        if result.get("pages_skipped"):
            click.echo(f"  Pages skipped: {len(result['pages_skipped'])}")
            for page in result["pages_skipped"]:
                click.echo(f"    ! {page}")
        click.echo("Done.")
    except Exception as e:
        _error_exit(e)


@cli.command()
@click.option("--incremental/--full", default=True, help="Incremental (default) or full recompile")
def compile(incremental: bool):
    """Compile wiki pages from raw sources."""
    from kb.compile.compiler import compile_wiki

    mode = "incremental" if incremental else "full"
    click.echo(f"Compiling ({mode})...")
    try:
        result = compile_wiki(incremental=incremental)
        click.echo(f"  Sources processed: {result['sources_processed']}")
        click.echo(f"  Pages created: {len(result['pages_created'])}")
        click.echo(f"  Pages updated: {len(result['pages_updated'])}")
        if result["errors"]:
            click.echo(f"  Errors: {len(result['errors'])}")
            for err in result["errors"]:
                click.echo(f"    ! {err['source']}: {err['error']}", err=True)
            ctx = click.get_current_context()
            ctx.exit(1)
        click.echo("Done.")
    except Exception as e:
        _error_exit(e)


@cli.command()
@click.argument("question")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "markdown", "marp", "html", "chart", "jupyter"]),
    default="text",
    help="Output format. 'text' prints to stdout; others write to outputs/.",
)
def query(question: str, output_format: str):
    """Query the knowledge base."""
    from kb.query.citations import format_citations
    from kb.query.engine import query_wiki

    click.echo(f"Querying: {question}\n")
    try:
        fmt_kwarg = None if output_format == "text" else output_format
        result = query_wiki(question, output_format=fmt_kwarg)
        click.echo(result["answer"])
        if result.get("citations"):
            click.echo(format_citations(result["citations"]))
        click.echo(f"\n[Searched {len(result.get('source_pages', []))} pages]")
        if result.get("output_path"):
            click.echo(f"\nOutput: {result['output_path']} ({result['output_format']})")
        if result.get("output_error"):
            click.echo(f"\n[warn] Output format failed: {result['output_error']}", err=True)
    except Exception as e:
        _error_exit(e)


@cli.command()
@click.option("--fix", is_flag=True, help="Auto-fix broken wikilinks (replace with plain text).")
@click.option(
    "--augment",
    is_flag=True,
    help="Reactive gap-fill: propose URLs for stub pages.",
)
@click.option(
    "--execute",
    is_flag=True,
    help="With --augment: fetch URLs + save to raw/. Requires --augment.",
)
@click.option(
    "--auto-ingest",
    is_flag=True,
    help="With --execute: also pre-extract + ingest. Requires --execute.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="With --augment: preview without writing anything.",
)
@click.option(
    "--max-gaps",
    type=int,
    default=5,
    help="Max stub gaps to attempt (≤10).",
)
@click.option(
    "--wiki-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Override wiki directory.",
)
@click.option(
    "--resume",
    type=str,
    default="",
    help=(
        "Resume an incomplete augment run by its 8-hex-char id "
        "(e.g. --resume=abc12345). Requires --augment."
    ),
)
def lint(
    fix: bool,
    augment: bool,
    execute: bool,
    auto_ingest: bool,
    dry_run: bool,
    max_gaps: int,
    wiki_dir: Path | None,
    resume: str,
):
    """Run lint checks on the wiki. Add --augment for reactive gap-fill."""
    from kb.config import AUGMENT_FETCH_MAX_CALLS_PER_RUN
    from kb.lint.runner import format_report, run_all_checks
    from kb.mcp.app import _validate_run_id

    # Flag dependency validation
    if execute and not augment:
        raise click.UsageError("--execute requires --augment")
    if auto_ingest and not execute:
        raise click.UsageError("--auto-ingest requires --execute (and --augment)")
    # Cycle 17 AC12 — --resume requires --augment; validated before forwarding.
    if resume and not augment:
        raise click.UsageError("--resume requires --augment")
    if resume:
        err = _validate_run_id(resume)
        if err:
            raise click.UsageError(err)
    # B4 (Phase 5 three-round MEDIUM): reject non-positive values up front so
    # negative --max-gaps doesn't silently truncate proposals via Python slicing.
    if max_gaps < 1:
        raise click.UsageError(f"--max-gaps={max_gaps} must be a positive integer")
    if max_gaps > AUGMENT_FETCH_MAX_CALLS_PER_RUN:
        raise click.UsageError(
            f"--max-gaps={max_gaps} exceeds hard ceiling "
            f"AUGMENT_FETCH_MAX_CALLS_PER_RUN={AUGMENT_FETCH_MAX_CALLS_PER_RUN}"
        )

    click.echo("Running lint checks...")
    try:
        report = run_all_checks(wiki_dir=wiki_dir, fix=fix)
        click.echo(format_report(report))
        if report.get("fixes_applied"):
            click.echo(f"\nAuto-fixed {len(report['fixes_applied'])} issue(s):")
            for f in report["fixes_applied"]:
                click.echo(f"  Fixed: {f['message']}")

        if augment:
            from kb.lint.augment import run_augment

            mode = "auto_ingest" if auto_ingest else ("execute" if execute else "propose")
            augment_result = run_augment(
                wiki_dir=wiki_dir,
                mode=mode,
                max_gaps=max_gaps,
                dry_run=dry_run,
                resume=resume or None,
            )
            click.echo("\n" + augment_result["summary"])

        if report["summary"].get("error", 0) > 0:
            raise SystemExit(1)
    except SystemExit:
        raise
    except click.UsageError:
        raise
    except Exception as e:
        _error_exit(e)


@cli.command()
def evolve():
    """Analyze gaps, suggest new connections and sources."""
    from kb.evolve.analyzer import format_evolution_report, generate_evolution_report

    click.echo("Analyzing knowledge gaps...\n")
    try:
        report = generate_evolution_report()
        click.echo(format_evolution_report(report))
    except Exception as e:
        _error_exit(e)


@cli.command()
def mcp():
    """Start the MCP server for Claude Code integration."""
    from kb.mcp_server import main as mcp_main

    try:
        mcp_main()
    except Exception as e:
        # Match the "MCP server failed to start" prefix for callers grepping
        # logs, but still surface the traceback when KB_DEBUG=1 / --verbose.
        if _is_debug_mode():
            click.echo(traceback.format_exc(), err=True)
        click.echo(f"Error: MCP server failed to start — {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--out-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Destination directory for publish outputs (default: PROJECT_ROOT/outputs).",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["llms", "llms-full", "graph", "siblings", "sitemap", "all"]),
    default="all",
    help=(
        "Which publish format(s) to emit. Defaults to 'all' "
        "(llms.txt + llms-full.txt + graph.jsonld + per-page siblings + sitemap)."
    ),
)
@click.option(
    "--incremental/--no-incremental",
    default=True,
    help=(
        "Skip regeneration when output files are newer than every wiki page "
        "(default: on). Use --no-incremental on first post-upgrade run so "
        "any pre-cycle-14 outputs are regenerated under the current "
        "epistemic filter (cycle-15 T10c)."
    ),
)
def publish(out_dir: Path | None, fmt: str, incremental: bool):
    """Publish wiki as /llms.txt, /llms-full.txt, and/or /graph.jsonld.

    Cycle 14 AC21 + Cycle 15 AC13. The output directory must either be
    inside PROJECT_ROOT (auto-created if missing) OR must already exist on
    disk (operator-managed path outside the project). Rejects UNC paths
    and paths that resolve outside PROJECT_ROOT and do not pre-exist.
    Path-containment check (threat T1) runs BEFORE flag plumbing so the
    cycle-15 ``--incremental/--no-incremental`` flag cannot bypass it
    (threat T8).
    """
    from kb.compile.publish import (
        build_graph_jsonld,
        build_llms_full_txt,
        build_llms_txt,
        build_per_page_siblings,
        build_sitemap_xml,
    )
    from kb.config import OUTPUTS_DIR, PROJECT_ROOT, WIKI_DIR

    target_dir = out_dir if out_dir is not None else OUTPUTS_DIR
    # Threat T1 — path containment: resolve, reject UNC and traversal
    # components, then verify either inside PROJECT_ROOT or pre-existing.
    target_str = str(target_dir)
    if ".." in Path(target_str).parts:
        raise click.UsageError(f"Refusing --out-dir with '..' traversal component: {target_dir}")
    try:
        resolved = Path(target_dir).resolve(strict=False)
    except OSError as exc:
        raise click.UsageError(f"Invalid --out-dir {target_dir!r}: {exc}") from exc
    # Reject UNC paths on Windows.
    if str(resolved).startswith("\\\\"):
        raise click.UsageError(f"Refusing UNC path for --out-dir: {target_dir}")
    # Allow if inside PROJECT_ROOT (via is_relative_to) OR pre-existing
    # operator-managed directory.
    inside_project = resolved.is_relative_to(PROJECT_ROOT)
    if not inside_project and not resolved.is_dir():
        raise click.UsageError(
            f"--out-dir {target_dir} is outside PROJECT_ROOT and does not pre-exist. "
            "Create it first or choose a path inside the project."
        )
    resolved.mkdir(parents=True, exist_ok=True)

    try:
        if fmt in ("llms", "all"):
            p = build_llms_txt(WIKI_DIR, resolved / "llms.txt", incremental=incremental)
            click.echo(f"wrote {p}")
        if fmt in ("llms-full", "all"):
            p = build_llms_full_txt(WIKI_DIR, resolved / "llms-full.txt", incremental=incremental)
            click.echo(f"wrote {p}")
        if fmt in ("graph", "all"):
            p = build_graph_jsonld(WIKI_DIR, resolved / "graph.jsonld", incremental=incremental)
            click.echo(f"wrote {p}")
        # Cycle 16 AC23/AC24 — per-page siblings + sitemap formats.
        if fmt in ("siblings", "all"):
            written = build_per_page_siblings(WIKI_DIR, resolved, incremental=incremental)
            click.echo(f"wrote {len(written)} per-page siblings under {resolved / 'pages'}/")
        if fmt in ("sitemap", "all"):
            p = build_sitemap_xml(WIKI_DIR, resolved / "sitemap.xml", incremental=incremental)
            click.echo(f"wrote {p}")
    except Exception as exc:
        _error_exit(exc)


@cli.command("refine-sweep")
@click.option(
    "--age-hours",
    type=int,
    default=168,
    help="Threshold in hours — rows older than this are candidates (>= 1).",
)
@click.option(
    "--action",
    type=click.Choice(["mark_failed", "delete"]),
    default="mark_failed",
    help="Action to apply to candidates (mark_failed is reversible by inspection).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="List candidates without mutating anything.",
)
def refine_sweep(age_hours: int, action: str, dry_run: bool):
    """Sweep stale refine-history pending rows (cycle 20 AC15).

    Flips or removes ``status="pending"`` rows older than ``--age-hours``.
    ``--action=delete`` writes an audit entry to ``wiki/log.md`` BEFORE the
    mutation. ``--dry-run`` previews candidates without touching disk.
    """
    import json as _json  # noqa: PLC0415

    from kb.review.refiner import sweep_stale_pending  # noqa: PLC0415

    try:
        result = sweep_stale_pending(hours=age_hours, action=action, dry_run=dry_run)
    except Exception as exc:
        _error_exit(exc)
    click.echo(_json.dumps(result, indent=2, sort_keys=True, default=str))


@cli.command("refine-list-stale")
@click.option(
    "--hours",
    type=int,
    default=24,
    help="Threshold in hours. Rows pending longer than this are returned.",
)
def refine_list_stale(hours: int):
    """List refine-history pending rows older than ``--hours`` (cycle 20 AC18).

    Returns the FULL helper dict (including ``revision_notes``) — this is the
    CLI local-use exception to the MCP-side ``notes_length`` projection.
    """
    import json as _json  # noqa: PLC0415

    from kb.review.refiner import list_stale_pending  # noqa: PLC0415

    if hours < 1:
        raise click.UsageError(f"--hours={hours} must be a positive integer")
    try:
        rows = list_stale_pending(hours=hours)
    except Exception as exc:
        _error_exit(exc)
    click.echo(_json.dumps(rows, indent=2, sort_keys=True, default=str))


@cli.command("rebuild-indexes")
@click.option(
    "--wiki-dir",
    "wiki_dir",
    type=click.Path(exists=True, file_okay=False, path_type=str),
    default=None,
    help="Target wiki directory (defaults to WIKI_DIR from config).",
)
@click.option(
    "--yes",
    "-y",
    "assume_yes",
    is_flag=True,
    default=False,
    help="Skip the confirmation prompt (for non-interactive callers).",
)
def rebuild_indexes_cmd(wiki_dir: str | None, assume_yes: bool):
    """Wipe derived indices (manifest + vector DB + LRU caches).

    Cycle 23 AC3. Next compile re-ingests all sources from scratch.
    Imports ``kb.compile.compiler`` lazily so the ``kb --version`` fast-path
    (cycle 8 L1) is not penalised by this subcommand's existence.
    """
    target = f" for {wiki_dir}" if wiki_dir else ""
    if not assume_yes:
        click.confirm(
            f"Wipe manifest + vector index + in-process caches{target}? "
            "The next compile will re-ingest every raw source.",
            abort=True,
        )

    from kb.compile.compiler import (  # noqa: PLC0415 — function-local per cycle-23 AC4 boot-lean
        _audit_token,
    )
    from kb.compile.compiler import (
        rebuild_indexes as _rebuild,
    )

    try:
        result = _rebuild(wiki_dir=Path(wiki_dir) if wiki_dir else None)
    except Exception as exc:
        _error_exit(exc)

    # Cycle 29 Q4 — CLI mirrors the compound audit token used by wiki/log.md so
    # the interactive operator sees the same `cleared (warn: tmp: <msg>)` form
    # (Q4 same-class-peer rule — both surfaces render from the same result dict).
    manifest_status = _audit_token(result["manifest"])
    vector_status = _audit_token(result["vector"])
    click.echo(
        f"manifest={manifest_status} "
        f"vector={vector_status} "
        f"caches_cleared={len(result['caches_cleared'])} "
        f"audit_written={result['audit_written']}"
    )


@cli.command()
@click.argument("query")
@click.option(
    "--limit",
    "limit",
    type=int,
    default=10,
    help="Maximum results to return (capped at MAX_SEARCH_RESULTS).",
)
@click.option(
    "--wiki-dir",
    "wiki_dir",
    type=click.Path(exists=True, file_okay=False, resolve_path=True),
    default=None,
    help="Wiki directory override (defaults to config WIKI_DIR).",
)
def search(query: str, limit: int, wiki_dir: str | None):
    """Search wiki pages by keyword (BM25 + optional vector fusion).

    Cycle 27 AC1 — CLI parity for MCP `kb_search`. Prints ranked results with
    type, score, title, snippet, and `[STALE]` markers. Query length and
    result-count caps match the MCP tool (MAX_QUESTION_LEN, MAX_SEARCH_RESULTS).
    """
    # Function-local imports preserve cycle-23 AC4 boot-lean contract.
    from kb.config import MAX_QUESTION_LEN, MAX_SEARCH_RESULTS  # noqa: PLC0415
    from kb.mcp.app import _validate_wiki_dir  # noqa: PLC0415
    from kb.mcp.browse import _format_search_results  # noqa: PLC0415
    from kb.query.engine import search_pages  # noqa: PLC0415

    if not query or not query.strip():
        click.echo("Error: Query cannot be empty.", err=True)
        sys.exit(1)
    if len(query) > MAX_QUESTION_LEN:
        click.echo(
            f"Error: Query too long ({len(query)} chars; max {MAX_QUESTION_LEN}).",
            err=True,
        )
        sys.exit(1)
    capped = max(1, min(limit, MAX_SEARCH_RESULTS))
    # Cycle-27 R1 Sonnet minor — thread `--wiki-dir` through the cycle-23
    # dual-anchor containment validator for pattern consistency with `kb stats`
    # (which routes through `kb_stats` and gets the check for free). Prevents
    # future write-capable refactors from inheriting an unchecked path.
    wiki_path, validation_err = _validate_wiki_dir(wiki_dir)
    if validation_err:
        click.echo(f"Error: {validation_err}", err=True)
        sys.exit(1)
    try:
        results = search_pages(query, wiki_dir=wiki_path, max_results=capped)
        click.echo(_format_search_results(results))
    except Exception as exc:
        _error_exit(exc)


@cli.command()
@click.option(
    "--wiki-dir",
    "wiki_dir",
    type=click.Path(exists=True, file_okay=False, resolve_path=True),
    default=None,
    help="Wiki directory override (defaults to config WIKI_DIR).",
)
def stats(wiki_dir: str | None):
    """Print wiki health snapshot (page counts, orphans, dead links).

    Cycle 27 AC2 — CLI parity for MCP `kb_stats`. Forwards to the same
    underlying library helpers.
    """
    from kb.mcp.browse import kb_stats  # noqa: PLC0415

    try:
        output = kb_stats(wiki_dir=wiki_dir)
        if output.startswith("Error:"):
            click.echo(output, err=True)
            sys.exit(1)
        click.echo(output)
    except Exception as exc:
        _error_exit(exc)


@cli.command("list-pages")
@click.option(
    "--type",
    "page_type",
    type=str,
    default="",
    help="Filter by page type (summary / entity / concept / comparison / synthesis).",
)
@click.option("--limit", type=int, default=200, help="Maximum pages to list.")
@click.option("--offset", type=int, default=0, help="Skip this many pages before listing.")
def list_pages(page_type: str, limit: int, offset: int):
    """Enumerate wiki pages (optionally filtered by type).

    Cycle 27 AC3 — CLI parity for MCP `kb_list_pages`. `--wiki-dir` override
    is NOT supported this cycle (Q4 — MCP tool signature would need to change;
    deferred to a future parity cycle).
    """
    from kb.mcp.browse import kb_list_pages  # noqa: PLC0415

    try:
        output = kb_list_pages(page_type=page_type, limit=limit, offset=offset)
        if output.startswith("Error:"):
            click.echo(output, err=True)
            sys.exit(1)
        click.echo(output)
    except Exception as exc:
        _error_exit(exc)


@cli.command("list-sources")
@click.option("--limit", type=int, default=200, help="Maximum sources to list.")
@click.option("--offset", type=int, default=0, help="Skip this many sources before listing.")
def list_sources(limit: int, offset: int):
    """Enumerate raw sources with their wiki backlinks.

    Cycle 27 AC4 — CLI parity for MCP `kb_list_sources`. `--wiki-dir` override
    is NOT supported this cycle (Q4 — MCP tool signature would need to change).
    """
    from kb.mcp.browse import kb_list_sources  # noqa: PLC0415

    try:
        output = kb_list_sources(limit=limit, offset=offset)
        if output.startswith("Error:"):
            click.echo(output, err=True)
            sys.exit(1)
        click.echo(output)
    except Exception as exc:
        _error_exit(exc)


@cli.command("graph-viz")
@click.option(
    "--max-nodes",
    "max_nodes",
    type=int,
    default=30,
    help="Max nodes in graph (default 30; 1-500; 0 rejected).",
)
@click.option(
    "--wiki-dir",
    "wiki_dir",
    type=click.Path(exists=True, file_okay=False, resolve_path=True),
    default=None,
    help="Wiki directory override (defaults to config WIKI_DIR).",
)
def graph_viz(max_nodes: int, wiki_dir: str | None):
    """Export the wiki knowledge graph as a Mermaid diagram.

    Cycle 30 AC2 — CLI parity for MCP `kb_graph_viz`. Forwards to the
    same underlying library helper; auto-prunes to the most-connected
    nodes when the graph exceeds ``max_nodes``.
    """
    from kb.mcp.health import kb_graph_viz  # noqa: PLC0415

    try:
        output = kb_graph_viz(max_nodes=max_nodes, wiki_dir=wiki_dir)
        if output.startswith("Error:"):
            click.echo(output, err=True)
            sys.exit(1)
        click.echo(output)
    except Exception as exc:
        _error_exit(exc)


@cli.command("verdict-trends")
@click.option(
    "--wiki-dir",
    "wiki_dir",
    type=click.Path(exists=True, file_okay=False, resolve_path=True),
    default=None,
    help="Wiki directory override (defaults to config WIKI_DIR).",
)
def verdict_trends(wiki_dir: str | None):
    """Show verdict quality trends over time.

    Cycle 30 AC3 — CLI parity for MCP `kb_verdict_trends`. Forwards to
    the same underlying library helper; reports weekly pass/fail/warning
    rates and whether quality is improving, stable, or declining.
    """
    from kb.mcp.health import kb_verdict_trends  # noqa: PLC0415

    try:
        output = kb_verdict_trends(wiki_dir=wiki_dir)
        if output.startswith("Error:"):
            click.echo(output, err=True)
            sys.exit(1)
        click.echo(output)
    except Exception as exc:
        _error_exit(exc)


if __name__ == "__main__":
    cli()
