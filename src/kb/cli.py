"""CLI entry point for knowledge base operations."""

from pathlib import Path

import click

from kb import __version__


@click.group()
@click.version_option(__version__)
def cli():
    """LLM Knowledge Base — compile raw sources into a structured wiki."""


@cli.command()
@click.argument("source_path")
@click.option(
    "--type",
    "source_type",
    type=click.Choice(
        [
            "article",
            "paper",
            "repo",
            "video",
            "podcast",
            "book",
            "dataset",
            "conversation",
        ]
    ),
    help="Source type (auto-detected if omitted)",
)
def ingest(source_path: str, source_type: str | None):
    """Ingest a raw source into the knowledge base."""
    from kb.ingest.pipeline import ingest_source

    source = Path(source_path).resolve()
    click.echo(f"Ingesting: {source}")
    try:
        result = ingest_source(source, source_type)
        # Fix 10.1: Show duplicate indicator if detected
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
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


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
        click.echo("Done.")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@cli.command()
@click.argument("question")
def query(question: str):
    """Query the knowledge base."""
    from kb.query.citations import format_citations
    from kb.query.engine import query_wiki

    click.echo(f"Querying: {question}\n")
    try:
        result = query_wiki(question)
        click.echo(result["answer"])
        if result["citations"]:
            click.echo(format_citations(result["citations"]))
        click.echo(f"\n[Searched {len(result['source_pages'])} pages]")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@cli.command()
@click.option("--fix/--no-fix", default=False, help="Auto-fix issues (default: report only)")
def lint(fix: bool):
    """Run health checks on the wiki."""
    from kb.lint.runner import format_report, run_all_checks

    click.echo("Running lint checks...")
    try:
        report = run_all_checks(fix=fix)
        click.echo(format_report(report))
        if report.get("fixes_applied"):
            click.echo(f"\nAuto-fixed {len(report['fixes_applied'])} issue(s):")
            for f in report["fixes_applied"]:
                click.echo(f"  Fixed: {f['message']}")
        # Fix 10.3: Exit with code 1 if any errors found
        if report["summary"].get("error", 0) > 0:
            raise SystemExit(1)
    except SystemExit:
        raise
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@cli.command()
def evolve():
    """Analyze gaps, suggest new connections and sources."""
    from kb.evolve.analyzer import format_evolution_report, generate_evolution_report

    click.echo("Analyzing knowledge gaps...\n")
    try:
        report = generate_evolution_report()
        click.echo(format_evolution_report(report))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@cli.command()
def mcp():
    """Start the MCP server for Claude Code integration."""
    from kb.mcp_server import main as mcp_main

    try:
        mcp_main()
    except Exception as e:
        click.echo(f"Error: MCP server failed to start — {e}", err=True)
        raise SystemExit(1)


if __name__ == "__main__":
    cli()
