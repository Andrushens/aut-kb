# Operator runbook — `autism-corpus`

Practical instructions for the human running the pipeline. The PRD lives at
`/root/.claude/plans/prd-autism-rag-nested-twilight.md`; this file is the
day-to-day reference.

## Prerequisites

- Python 3.12 (`uv` will manage the venv).
- `uv >= 0.8`.
- ~10–20 GB disk for the PMC OA bulk download (only when `pmc-oa-autism` is enabled).

## First-time setup

```bash
git clone <repo>
cd aut-kb
uv sync --extra dev
uv run pytest -q          # sanity: should be 189 green
uv run autism-corpus --help
```

## A normal build

```bash
uv run autism-corpus build --all
```

This runs every registered adapter except `pmc-oa-autism`, writes:

- `output/<run_id>/documents.jsonl`
- `output/<run_id>/chunks.jsonl`
- `output/<run_id>/manifest.json`
- `output/<run_id>/report.html`

Open the report in a browser — it lists per-source counts, licence breakdown,
dropped documents, and items flagged for review.

`run_id` defaults to `YYYY-MM-DDTHH-MM-SS` (UTC). Override with `--run-id`.

### Limiting a build for development

```bash
uv run autism-corpus build --only nhs-autism --limit 5
```

`--only` may be passed multiple times. `--limit N` caps each source to N
items.

### Re-rendering the report only

```bash
uv run autism-corpus report --run-id 2026-05-14T09-00-00
```

Use this when you change the report template and want to re-render without
re-fetching.

## Weekly re-run

The cache (`cache/`) is content-addressed and HTTP-revalidated via
`If-None-Match` / `If-Modified-Since`. A second run a week later only
re-downloads what genuinely changed at the source. To force a complete
re-fetch for one source:

```bash
uv run autism-corpus build --only nhs-autism --limit 5 \
    && rm -rf cache/nhs-autism
```

(`--force` on `fetch` exists for debugging individual URLs.)

## Adding a URL to the exclude list

Some pages on tier-1 sources turn out to be empty redirects, off-topic, or
contain content we deliberately want out. Edit `data/excluded_urls.yaml`:

```yaml
urls:
  - https://www.nhs.uk/conditions/autism/some-unwanted-page/
  - https://www.cdc.gov/autism/some-misleading-page/
```

These are matched exactly against each document's `canonical_url`. The next
build drops them with reason `excluded` in the report.

## Adding a new seed URL

For sources without sitemaps (NICE, WHO, NIH/NIMH, MedlinePlus, CDC LTSAE):

```yaml
# data/seed_urls.yaml
nih-nimh:
  - item_id: my-new-topic
    url: https://www.nimh.nih.gov/health/topics/my-new-topic
```

Re-run `autism-corpus build --only nih-nimh` to pick it up.

## Enabling the PMC OA adapter

PMC OA Commercial Use is a multi-GB bulk corpus that lives on AWS RODA
(`s3://pmc-oa-opendata/...`) and NCBI FTP. The MVP pipeline ships the
adapter logic (`adapters/pmc_oa.py`) with two injection points:

- `file_list_source`: an iterable of `FileListEntry` rows, normally streamed
  from `oa_file_list.csv`.
- `article_loader`: a callable that returns JATS XML bytes for a given entry.

The CLI's `build` does **not** wire these up — they require operator-supplied
credentials and a real bulk-download decision. To run PMC end-to-end, use
the Python API directly:

```python
from autism_corpus.adapters.pmc_oa import PmcOaAdapter
from autism_corpus.pipeline import run_build
from autism_corpus.utils.http import CachedHttpClient

adapter = PmcOaAdapter(
    http_client=CachedHttpClient(source_id="pmc-oa-autism", cache_dir="cache"),
    file_list_source=my_csv_streamer,
    article_loader=my_s3_loader,
)
run_build([adapter], output_root="output", run_id="2026-05-14-pmc-only")
```

Add a `--limit N` to `discover` while iterating; otherwise budget hours on the
initial fetch.

## What to audit before publishing a build

Open `report.html` and check:

1. **Per-source documents** — each source returned roughly the expected count.
   Zero from a source that should produce hundreds → adapter broken.
2. **Licence breakdown** — every chunk has a licence string. Unknown values
   indicate a parsing bug.
3. **Flagged for review** — open the linked URL; if the document is genuinely
   off-topic, add the URL to `data/excluded_urls.yaml` and re-run.
4. **Sample documents** — eyeball ~20 titles. Off-topic titles indicate
   either an adapter bug or a content drift at the source.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `autism-corpus build --all` exits with `No adapters to run.` | Registry empty — check no recent change removed adapter imports from `cli._ADAPTER_MODULES`. |
| Tests fail after pulling | Run `uv sync --extra dev` to update deps. |
| `mypy --strict` complains about pymupdf | Already suppressed with line-scoped `# type: ignore`. Don't widen. |
| A source HTML page returns gibberish | Inspect `cache/<source-id>/<hash>.raw` — likely a Cloudflare interstitial or login wall. Update the adapter to detect & skip. |

## Code review for new adapters

When adding a 9th adapter:

1. Subclass `SourceAdapter`, set the four class attrs.
2. Decorate the class with `@register_adapter`.
3. Add the module to `cli._ADAPTER_MODULES` so `build --all` imports it.
4. Write tests against mocked HTTP via `respx`; commit fixtures, never live
   payloads.
5. Update `report.html`'s site-prefix map in `pipeline.DEFAULT_SITE_PREFIXES`.
