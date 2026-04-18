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
def lint(
    fix: bool,
    augment: bool,
    execute: bool,
    auto_ingest: bool,
    dry_run: bool,
    max_gaps: int,
    wiki_dir: Path | None,
):
    """Run lint checks on the wiki. Add --augment for reactive gap-fill."""
    from kb.config import AUGMENT_FETCH_MAX_CALLS_PER_RUN
    from kb.lint.runner import format_report, run_all_checks

    # Flag dependency validation
    if execute and not augment:
        raise click.UsageError("--execute requires --augment")
    if auto_ingest and not execute:
        raise click.UsageError("--auto-ingest requires --execute (and --augment)")
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


if __name__ == "__main__":
    cli()
