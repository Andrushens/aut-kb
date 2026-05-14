from __future__ import annotations

import typer

app = typer.Typer(
    name="autism-corpus",
    help="Build a licensed, attributed autism knowledge corpus for RAG.",
    no_args_is_help=True,
)


@app.command()
def discover(
    source: str = typer.Option(..., "--source", help="Source id, e.g. nhs-autism"),
) -> None:
    """List items available from a source without fetching them."""
    typer.echo(f"discover: {source} (not implemented)")


@app.command()
def fetch(
    source: str = typer.Option(..., "--source"),
    limit: int | None = typer.Option(None, "--limit", help="Max items to fetch"),
    force: bool = typer.Option(False, "--force", help="Bypass on-disk cache"),
) -> None:
    """Fetch raw payloads for a source into the cache directory."""
    typer.echo(f"fetch: {source} limit={limit} force={force} (not implemented)")


@app.command()
def parse(
    source: str = typer.Option(..., "--source"),
) -> None:
    """Parse cached raw payloads into ParsedDocument objects on disk."""
    typer.echo(f"parse: {source} (not implemented)")


@app.command()
def normalize(
    all_: bool = typer.Option(False, "--all", help="Normalize across all sources"),
) -> None:
    """Run text normalization across parsed documents."""
    typer.echo(f"normalize: all={all_} (not implemented)")


@app.command()
def chunk(
    all_: bool = typer.Option(False, "--all", help="Chunk across all sources"),
) -> None:
    """Sentence-aware chunking of normalised documents."""
    typer.echo(f"chunk: all={all_} (not implemented)")


@app.command()
def build(
    all_: bool = typer.Option(False, "--all", help="Build the corpus end-to-end"),
    offline: bool = typer.Option(False, "--offline", help="Use VCR cassettes; no network"),
    limit: int | None = typer.Option(None, "--limit", help="Cap items per source"),
    include_pmc: bool = typer.Option(True, "--include-pmc/--no-pmc"),
) -> None:
    """Run the full pipeline end-to-end across all registered adapters."""
    typer.echo(
        f"build: all={all_} offline={offline} limit={limit} include_pmc={include_pmc} "
        "(not implemented)"
    )


@app.command()
def report(
    run_id: str = typer.Option(..., "--run-id"),
) -> None:
    """Render report.html for a build run."""
    typer.echo(f"report: {run_id} (not implemented)")


if __name__ == "__main__":
    app()
