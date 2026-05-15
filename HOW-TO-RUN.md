# Running `autism-corpus`

The shortest path from clone to a real corpus build.

## 1. Install

```bash
git clone <this-repo> aut-kb
cd aut-kb
uv sync --extra dev
uv run autism-corpus --help      # sanity: lists 7 subcommands
uv run pytest -q                 # sanity: 190 green
```

Requires **Python 3.12** and **`uv` ≥ 0.8**. `uv` installs everything else
into `.venv/`.

## 2. Things you must change before a real run

The MVP ships with placeholder data and a couple of operator-supplied seams.
Edit these or your build will either fail or hit `example.test` URLs.

### a. `data/seed_urls.yaml`

Replace the `example.test` URLs with real production URLs for the five
seed-driven adapters. Schema:

```yaml
nice-guidelines:
  - item_id: cg128                          # stable id; used in chunk_id
    url: https://www.nice.org.uk/.../CG128.pdf
cdc-ltsae:
  - item_id: milestones-overview
    url: https://www.cdc.gov/ncbddd/actearly/...
    kind: html                              # or "pdf"
nih-nimh:
  - { item_id: asd, url: https://www.nimh.nih.gov/health/topics/... }
medlineplus-autism:
  - { item_id: asd, url: https://medlineplus.gov/autismspectrumdisorder.html }
who-autism:
  - { item_id: fact-sheet, url: https://www.who.int/news-room/fact-sheets/...,
      kind: html }
```

`item_id` and `url` are required; `kind` defaults to `html`.

### b. Your contact email in the User-Agent

`src/autism_corpus/config.py:11`:

```python
USER_AGENT = "autism-corpus/1.0 (+contact@yourdomain)"
```

Change `contact@yourdomain` to a mailbox you actually read. CDC, NHS, and
PMC operators will use this to contact you about crawl behaviour.

### c. `data/excluded_urls.yaml`

Starts empty:

```yaml
urls: []
```

After your first build, open `output/<run_id>/report.html`, find any
off-topic / pseudoscience / boilerplate pages, and add their
`canonical_url` here. They'll be dropped on the next build.

## 3. Run

```bash
uv run autism-corpus build --all
```

Writes to `output/<run_id>/`:

| File | What it is |
|---|---|
| `documents.jsonl` | one ParsedDocument per line (post-filter, post-dedup) |
| `chunks.jsonl` | one Chunk per line — feed this to your embedding service |
| `manifest.json` | counts per source, licence breakdown, input hash |
| `report.html` | human-readable summary; open in a browser |

`run_id` defaults to `YYYY-MM-DDTHH-MM-SS` (UTC). Override with
`--run-id <name>`.

### Useful flags

```bash
--only nhs-autism              # one source only; repeatable
--limit 10                     # cap items per source (dev runs)
--output-root /path/to/output  # override default ./output
--cache-root  /path/to/cache   # override default ./cache
```

### Re-render the report only

```bash
uv run autism-corpus report --run-id 2026-05-14T09-00-00
```

## 4. The PMC OA adapter is opt-in

`pmc-oa-autism` is skipped by `build --all` because it needs two
operator-supplied callables: `file_list_source` (stream of
`oa_file_list.csv` rows from NCBI FTP or AWS RODA bucket
`pmc-oa-opendata`) and `article_loader` (fetch JATS XML bytes for a row).
Wire them via the Python API:

```python
from autism_corpus.adapters.pmc_oa import PmcOaAdapter
from autism_corpus.pipeline import run_build
from autism_corpus.utils.http import CachedHttpClient

adapter = PmcOaAdapter(
    http_client=CachedHttpClient(source_id="pmc-oa-autism", cache_dir="cache"),
    file_list_source=my_csv_streamer,        # () -> Iterable[FileListEntry]
    article_loader=my_s3_loader,             # (FileListEntry) -> bytes
)
run_build([adapter], output_root="output")
```

## 5. Caching, rate limits, politeness

- The HTTP client (`utils/http.py`) is rate-limited per host (1 req/s by
  default) and writes a content-addressed cache to `cache/<source-id>/`.
- Subsequent runs revalidate via `If-None-Match` / `If-Modified-Since`.
  Clear the cache for a single source with `rm -rf cache/<source-id>`.
- `robots.txt` is fetched once per host and respected. Note: stdlib
  `RobotFileParser` uses first-match-wins, not RFC 9309 longest-match —
  this is conservative on purpose.

## 6. Adding a new adapter

1. Create `src/autism_corpus/adapters/<my_source>.py` extending
   `SourceAdapter`, set `source_id`, `licence`, `licence_url`,
   `attribution_template` class attrs.
2. Implement `discover() / fetch() / parse()` — use
   `adapters.common.build_parsed_document` and `http_get_as_raw_document`.
3. Decorate the class with `@register_adapter`.
4. Add the module path to `src/autism_corpus/cli.py:_ADAPTER_MODULES`
   so `build --all` imports it.
5. Add an entry to `pipeline.DEFAULT_SITE_PREFIXES` for the breadcrumb
   display label.
6. Add tests under `tests/adapters/test_<my_source>.py` using `respx`.

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| `No adapters to run` | Pass `--all` or `--only <id>`; check `cli._ADAPTER_MODULES`. |
| Source has `discovered=1` but `documents=0` in manifest | Doc dropped by filter — likely under 200-token min after extraction, or recency >10 years. Check `report.html`'s "Dropped documents" table. |
| All chunks dedupe to one source | Multiple sources serving identical text. Cleanest licence wins per `dedup._LICENCE_PRIORITY`; the dropped sources won't appear in the manifest. |
| `RESPX: some routes were not called` in tests | Test mocked a URL the adapter didn't hit; remove the unused mock or fix the adapter URL. |
| Cache reads stale payload | `rm -rf cache/<source-id>/` and re-run. |
| `uv run autism-corpus` reports `ModuleNotFoundError: autism_corpus` | `uv pip install -e .` once, then `uv sync` from then on. |

## 8. Files of interest

```
src/autism_corpus/
├── cli.py              # typer commands; registry import list
├── pipeline.py         # run_build orchestration
├── report.py           # jinja2 → report.html
├── models.py           # ParsedDocument, Chunk, Manifest (pydantic v2 frozen)
├── adapters/
│   ├── base.py         # SourceAdapter ABC + register_adapter
│   ├── common.py       # build_parsed_document, http_get_as_raw_document
│   └── <8 adapters>
├── normalize/          # html (trafilatura), pdf (pymupdf), text (lingua)
├── chunk/              # sentence-aware chunker + breadcrumbs
├── dedup.py            # licence-priority-aware dedup
├── filters.py          # excluded-URL, recency, token-band filters
└── utils/              # http (rate-limit + cache + ETag), robots, hashing

data/
├── seed_urls.yaml      # edit this before real runs
└── excluded_urls.yaml  # add bad URLs after auditing

docs/
├── operator-runbook.md # day-to-day operator playbook
└── audit-v1.md         # MVP audit / known limitations
```
