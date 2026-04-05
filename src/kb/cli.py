"""CLI entry point for knowledge base operations."""

import click

from kb import __version__


@click.group()
@click.version_option(__version__)
def cli():
    """LLM Knowledge Base — compile raw sources into a structured wiki."""


@cli.command()
@click.argument("source_path")
@click.option("--type", "source_type", type=click.Choice([
    "article", "paper", "repo", "video", "podcast", "book", "dataset", "conversation",
]), help="Source type (auto-detected if omitted)")
def ingest(source_path: str, source_type: str | None):
    """Ingest a raw source into the knowledge base."""
    click.echo(f"Ingesting: {source_path}")
    # TODO: implement ingest pipeline


@cli.command()
@click.option("--incremental/--full", default=True, help="Incremental (default) or full recompile")
def compile(incremental: bool):
    """Compile wiki pages from raw sources."""
    mode = "incremental" if incremental else "full"
    click.echo(f"Compiling ({mode})...")
    # TODO: implement compile


@cli.command()
@click.argument("question")
def query(question: str):
    """Query the knowledge base."""
    click.echo(f"Querying: {question}")
    # TODO: implement query engine


@cli.command()
@click.option("--fix/--no-fix", default=False, help="Auto-fix issues (default: report only)")
def lint(fix: bool):
    """Run health checks on the wiki."""
    click.echo("Running lint checks...")
    # TODO: implement lint runner


@cli.command()
def evolve():
    """Analyze gaps, suggest new connections and sources."""
    click.echo("Analyzing knowledge gaps...")
    # TODO: implement evolve analyzer


if __name__ == "__main__":
    cli()
