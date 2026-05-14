"""End-to-end orchestration: discover → fetch → parse → dedup → filter → chunk.

The pipeline takes a list of `SourceAdapter` instances and produces three
artifacts under `output_root/{run_id}/`: `documents.jsonl`, `chunks.jsonl`, and
`manifest.json`. A separate `report.py` renders an HTML summary on top.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from autism_corpus import __version__
from autism_corpus.adapters.base import SourceAdapter
from autism_corpus.chunk.sentence_aware import chunk_document
from autism_corpus.dedup import deduplicate
from autism_corpus.filters import FilterConfig, FilterReport, apply_filters
from autism_corpus.models import Chunk, Manifest, ParsedDocument

DEFAULT_SITE_PREFIXES: Mapping[str, str] = {
    "cdc-autism": "CDC",
    "cdc-ltsae": "CDC LTSAE",
    "medlineplus-autism": "MedlinePlus",
    "nhs-autism": "NHS",
    "nice-guidelines": "NICE",
    "nih-nimh": "NIMH",
    "pmc-oa-autism": "PMC",
    "who-autism": "WHO",
    "stub-source": "Stub",
    "other-stub": "Other",
}


@dataclass(frozen=True)
class SourceStats:
    documents_discovered: int = 0
    documents_parsed: int = 0
    documents_kept: int = 0
    chunks_emitted: int = 0
    parse_errors: int = 0


@dataclass(frozen=True)
class BuildResult:
    run_id: str
    output_dir: Path
    documents_path: Path
    chunks_path: Path
    manifest_path: Path
    report_path: Path
    documents: list[ParsedDocument]
    chunks: list[Chunk]
    manifest: Manifest
    filter_report: FilterReport
    per_source: dict[str, SourceStats] = field(default_factory=dict)


def _new_run_id() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S")


def _collect_docs(
    adapters: Iterable[SourceAdapter],
    *,
    per_source: dict[str, SourceStats],
    limit_per_source: int | None,
) -> list[ParsedDocument]:
    docs: list[ParsedDocument] = []
    for adapter in adapters:
        sid = adapter.source_id
        discovered = 0
        parsed = 0
        errors = 0
        for index, ref in enumerate(adapter.discover()):
            if limit_per_source is not None and index >= limit_per_source:
                break
            discovered += 1
            try:
                raw = adapter.fetch(ref)
                docs.append(adapter.parse(raw))
                parsed += 1
            except Exception:
                errors += 1
        per_source[sid] = SourceStats(
            documents_discovered=discovered,
            documents_parsed=parsed,
            documents_kept=0,
            chunks_emitted=0,
            parse_errors=errors,
        )
    return docs


def _bump(
    per_source: dict[str, SourceStats],
    source_id: str,
    *,
    documents_kept: int = 0,
    chunks_emitted: int = 0,
) -> None:
    existing = per_source.get(source_id) or SourceStats()
    per_source[source_id] = SourceStats(
        documents_discovered=existing.documents_discovered,
        documents_parsed=existing.documents_parsed,
        documents_kept=existing.documents_kept + documents_kept,
        chunks_emitted=existing.chunks_emitted + chunks_emitted,
        parse_errors=existing.parse_errors,
    )


def _input_hash(docs: Iterable[ParsedDocument]) -> str:
    h = hashlib.sha256()
    for doc in sorted(docs, key=lambda d: (d.source_id, d.source_item_id)):
        h.update(doc.hash.encode("utf-8"))
    return h.hexdigest()


def run_build(
    adapters: Iterable[SourceAdapter],
    *,
    output_root: Path,
    run_id: str | None = None,
    site_prefixes: Mapping[str, str] | None = None,
    filter_config: FilterConfig | None = None,
    limit_per_source: int | None = None,
) -> BuildResult:
    """Run the full pipeline against the given adapters and write artifacts."""
    run_id = run_id or _new_run_id()
    output_dir = output_root / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    documents_path = output_dir / "documents.jsonl"
    chunks_path = output_dir / "chunks.jsonl"
    manifest_path = output_dir / "manifest.json"
    report_path = output_dir / "report.html"
    prefixes = dict(DEFAULT_SITE_PREFIXES)
    if site_prefixes is not None:
        prefixes.update(site_prefixes)
    per_source: dict[str, SourceStats] = {}

    raw_docs = _collect_docs(
        adapters, per_source=per_source, limit_per_source=limit_per_source
    )
    deduped = deduplicate(raw_docs)
    filter_report = apply_filters(deduped, filter_config or FilterConfig())
    kept_docs = list(filter_report.kept)

    all_chunks: list[Chunk] = []
    for doc in kept_docs:
        prefix = prefixes.get(doc.source_id, doc.source_id)
        doc_chunks = chunk_document(doc, site_prefix=prefix)
        all_chunks.extend(doc_chunks)
        _bump(
            per_source,
            doc.source_id,
            documents_kept=1,
            chunks_emitted=len(doc_chunks),
        )

    # Write documents.jsonl
    with documents_path.open("w", encoding="utf-8") as fh:
        for doc in kept_docs:
            fh.write(doc.model_dump_json())
            fh.write("\n")

    # Write chunks.jsonl
    with chunks_path.open("w", encoding="utf-8") as fh:
        for chunk in all_chunks:
            fh.write(chunk.model_dump_json())
            fh.write("\n")

    # Write manifest
    licence_counter: Counter[str] = Counter(c.licence for c in all_chunks)
    sources_block = {
        sid: {
            "documents": stats.documents_kept,
            "chunks": stats.chunks_emitted,
            "discovered": stats.documents_discovered,
            "parse_errors": stats.parse_errors,
        }
        for sid, stats in per_source.items()
    }
    manifest = Manifest(
        run_id=run_id,
        pipeline_version=__version__,
        sources=sources_block,
        licences=dict(licence_counter),
        input_hash=_input_hash(raw_docs) if raw_docs else "0" * 64,
        generated_at=datetime.now(UTC),
    )
    manifest_path.write_text(manifest.model_dump_json(indent=2))

    return BuildResult(
        run_id=run_id,
        output_dir=output_dir,
        documents_path=documents_path,
        chunks_path=chunks_path,
        manifest_path=manifest_path,
        report_path=report_path,
        documents=kept_docs,
        chunks=all_chunks,
        manifest=manifest,
        filter_report=filter_report,
        per_source=per_source,
    )


_ = json  # keep import for forward compatibility with reporting helpers
