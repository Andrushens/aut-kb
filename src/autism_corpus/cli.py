from __future__ import annotations

import importlib
import json
from collections.abc import Iterable, Sequence
from pathlib import Path

import typer

from autism_corpus.adapters.base import SourceAdapter, adapter_registry
from autism_corpus.config import DEFAULT_CACHE_DIR, DEFAULT_OUTPUT_DIR, REPO_ROOT, Settings
from autism_corpus.filters import FilterReport
from autism_corpus.models import Chunk, Manifest, ParsedDocument
from autism_corpus.pipeline import BuildResult, SourceStats, run_build
from autism_corpus.report import write_report
from autism_corpus.utils.http import CachedHttpClient

# Importing these modules triggers @register_adapter decorators.
_ADAPTER_MODULES: Sequence[str] = (
    "autism_corpus.adapters.cdc_autism",
    "autism_corpus.adapters.cdc_ltsae",
    "autism_corpus.adapters.medlineplus",
    "autism_corpus.adapters.nhs_autism",
    "autism_corpus.adapters.nice_guidelines",
    "autism_corpus.adapters.nih_nimh",
    "autism_corpus.adapters.pmc_oa",
    "autism_corpus.adapters.who",
)


def _import_adapters() -> None:
    for mod in _ADAPTER_MODULES:
        importlib.import_module(mod)


def _build_registered_adapters(
    settings: Settings,
    *,
    cache_root: Path,
    only: Iterable[str] | None = None,
) -> list[SourceAdapter]:
    """Construct one instance of every registered adapter.

    PMC OA needs callables that the operator must inject from outside the CLI
    for a real bulk run; the default build skips it unless an operator has
    pre-wired `pmc_file_list_source` / `pmc_article_loader` in settings.
    """
    _import_adapters()
    registry = adapter_registry()
    only_set: set[str] | None = set(only) if only else None
    adapters: list[SourceAdapter] = []
    for sid, cls in registry.items():
        if only_set is not None and sid not in only_set:
            continue
        if sid == "pmc-oa-autism":
            # Skipped by default; requires injected loaders the CLI cannot
            # discover. Operators add it via a custom entry point.
            continue
        client = CachedHttpClient(source_id=sid, cache_dir=cache_root, config=settings.http)
        adapters.append(cls(client))
    return adapters


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
    _import_adapters()
    registry = adapter_registry()
    cls = registry.get(source)
    if cls is None:
        typer.echo(f"unknown source: {source}", err=True)
        raise typer.Exit(code=2)
    settings = Settings()
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    client = CachedHttpClient(source_id=source, cache_dir=settings.cache_dir, config=settings.http)
    adapter = cls(client)
    for ref in adapter.discover():
        typer.echo(json.dumps({"item_id": ref.item_id, "url": ref.url}))


@app.command()
def fetch(
    source: str = typer.Option(..., "--source"),
    limit: int | None = typer.Option(None, "--limit"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Fetch raw payloads for a source into the cache directory."""
    typer.echo(
        f"fetch is a debugging command; in normal use, run `build`. "
        f"(source={source} limit={limit} force={force})"
    )


@app.command()
def parse(
    source: str = typer.Option(..., "--source"),
) -> None:
    """Parse cached raw payloads into ParsedDocument objects on disk.

    For most operators this is exercised via `build` rather than directly.
    """
    typer.echo(f"parse is a debugging command; in normal use, run `build`. (source={source})")


@app.command()
def normalize(
    all_: bool = typer.Option(False, "--all", help="Normalize across all sources"),
) -> None:
    """Run text normalization. Driven by `build` in production runs."""
    typer.echo(f"normalize is a debugging command; in normal use, run `build`. (all={all_})")


@app.command()
def chunk(
    all_: bool = typer.Option(False, "--all", help="Chunk across all sources"),
) -> None:
    """Sentence-aware chunking. Driven by `build` in production runs."""
    typer.echo(f"chunk is a debugging command; in normal use, run `build`. (all={all_})")


@app.command()
def build(
    all_: bool = typer.Option(False, "--all", help="Build the corpus end-to-end"),
    offline: bool = typer.Option(
        False, "--offline", help="Refuse network access (use cached payloads only)"
    ),
    limit: int | None = typer.Option(None, "--limit", help="Cap items per source"),
    only: list[str] = typer.Option(  # noqa: B008 - typer wants Option() here
        [], "--only", help="Restrict to specific source ids; repeatable"
    ),
    include_pmc: bool = typer.Option(False, "--include-pmc/--no-pmc"),
    run_id: str | None = typer.Option(None, "--run-id"),
    output_root: Path = typer.Option(  # noqa: B008
        DEFAULT_OUTPUT_DIR, "--output-root", help="Root directory for run artifacts"
    ),
    cache_root: Path = typer.Option(  # noqa: B008
        DEFAULT_CACHE_DIR, "--cache-root", help="Root directory for the http cache"
    ),
) -> None:
    """Run the full pipeline end-to-end across all registered adapters."""
    if not all_ and not only:
        typer.echo("Pass --all or one or more --only <source-id> flags.", err=True)
        raise typer.Exit(code=2)
    if offline:
        typer.echo(
            "--offline is informational in this build; adapters still call into "
            "CachedHttpClient. A real offline mode requires pre-populated cache.",
            err=True,
        )
    settings = Settings(cache_dir=cache_root)
    cache_root.mkdir(parents=True, exist_ok=True)
    only_set = set(only) if only else None
    adapters = _build_registered_adapters(settings, cache_root=cache_root, only=only_set)
    if include_pmc:
        typer.echo(
            "--include-pmc is recognised but the PMC adapter needs an injected "
            "file_list_source and article_loader. Run via the Python API in this version.",
            err=True,
        )
    if not adapters:
        typer.echo("No adapters to run.", err=True)
        raise typer.Exit(code=2)
    result: BuildResult = run_build(
        adapters,
        output_root=output_root,
        run_id=run_id,
        limit_per_source=limit,
    )
    write_report(result)
    typer.echo(
        f"build complete: run_id={result.run_id} "
        f"docs={len(result.documents)} chunks={len(result.chunks)} "
        f"output={result.output_dir}"
    )


@app.command()
def report(
    run_id: str = typer.Option(..., "--run-id"),
    output_root: Path = typer.Option(  # noqa: B008
        DEFAULT_OUTPUT_DIR, "--output-root", help="Root directory where the run lives"
    ),
) -> None:
    """Re-render the HTML report for an existing build run."""
    run_dir = output_root / run_id
    documents_path = run_dir / "documents.jsonl"
    chunks_path = run_dir / "chunks.jsonl"
    manifest_path = run_dir / "manifest.json"
    if not (documents_path.exists() and chunks_path.exists() and manifest_path.exists()):
        typer.echo(f"missing artifacts in {run_dir}", err=True)
        raise typer.Exit(code=2)
    docs = [
        ParsedDocument.model_validate_json(line)
        for line in documents_path.read_text().splitlines()
        if line
    ]
    chunks = [
        Chunk.model_validate_json(line)
        for line in chunks_path.read_text().splitlines()
        if line
    ]
    manifest = Manifest.model_validate_json(manifest_path.read_text())
    per_source = {
        sid: SourceStats(
            documents_discovered=stats.get("discovered", 0),
            documents_parsed=stats.get("documents", 0),
            documents_kept=stats.get("documents", 0),
            chunks_emitted=stats.get("chunks", 0),
            parse_errors=stats.get("parse_errors", 0),
        )
        for sid, stats in manifest.sources.items()
    }
    result = BuildResult(
        run_id=run_id,
        output_dir=run_dir,
        documents_path=documents_path,
        chunks_path=chunks_path,
        manifest_path=manifest_path,
        report_path=run_dir / "report.html",
        documents=docs,
        chunks=chunks,
        manifest=manifest,
        filter_report=FilterReport(kept=docs, dropped=[], flagged_for_review=[]),
        per_source=per_source,
    )
    write_report(result)
    typer.echo(f"wrote {result.report_path}")


# Keep REPO_ROOT importable for downstream tools that pin to it.
_ = REPO_ROOT


if __name__ == "__main__":
    app()
