# autism-corpus

Reproducible data pipeline that builds a licensed, attributed autism knowledge
corpus for retrieval-augmented generation. Lives inside the `aut-kb` repo and
ships as the Python package `autism_corpus` with the CLI `autism-corpus`.

The pipeline's job is **text only**: it discovers, fetches, normalises,
deduplicates, filters, and chunks documents from open-licensed sources. It
does not generate embeddings, does not run a vector database, and does not
implement the chatbot. Those live in separate downstream services.

## Quick start

```bash
uv sync                                       # install deps into .venv
uv run autism-corpus --help                   # list subcommands
uv run pytest -q                              # run the test suite
uv run autism-corpus build --all --offline    # build using VCR cassettes (no network)
```

## Sources in scope (v1)

Only Tier 1 sources (public domain or explicit open licence). See the PRD for
the full inventory. Permission-based sources (ASAN, AWN, Spectrum, Autism
Speaks) and Arabic content are explicit v2 work.

| Source ID | Origin | Licence |
|---|---|---|
| `cdc-autism` | CDC autism pages | Public domain (US Government) |
| `cdc-ltsae` | CDC "Learn the Signs. Act Early." | Public domain |
| `nih-nimh` | NIMH autism information | Public domain |
| `medlineplus-autism` | MedlinePlus | Public domain (NLM/NIH) |
| `nhs-autism` | NHS autism pages | OGL v3.0 |
| `nice-guidelines` | NICE CG128/CG142/CG170 PDFs | OGL v3.0 |
| `pmc-oa-autism` | PubMed Central OA Commercial Use | Article-level CC licences |
| `who-autism` | WHO autism fact sheets | CC BY-NC-SA 3.0 IGO |

## Output

The pipeline writes to `output/{run_id}/`:

- `documents.jsonl` — one parsed document per line (post-dedup, post-filter).
- `chunks.jsonl` — one chunk per line, ready for an embedding service.
- `manifest.json` — counts, licence breakdown, input hashes, pipeline version.
- `report.html` — human-readable summary for content review.

## Operator runbook

See [docs/operator-runbook.md](./docs/operator-runbook.md) (written in Batch 4).

## Layout

See the project plan at `/root/.claude/plans/prd-autism-rag-nested-twilight.md`
for the authoritative description of files and execution batches.

## Licence

The pipeline source is MIT. Each corpus document carries its own licence and
attribution; the manifest records them per chunk.
