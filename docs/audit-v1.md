# MVP v1.0 audit

Date: 2026-05-14
Branch: `claude/install-cache-skills-BupbL`
Final commit prior to audit: see `git log` (`8b7c7bb` at time of writing).

## Verification commands (output abridged)

```
$ uv run pytest -q --cov=autism_corpus
190 passed in 14.15s
TOTAL                                            1399    142    90%
```

Coverage **90%**, above the plan's 85% threshold. Lowest individual file
is `cli.py` at 61% — the debug subcommands (`fetch`, `parse`, `normalize`,
`chunk`) are no-op shims that emit a "use `build`" message and are not
themselves the test target. `pmc_oa.py` is at 84% because the production
S3/FTP loader path is intentionally injected (not exercised in tests).

```
$ uv run ruff check src/ tests/
All checks passed!

$ uv run mypy --strict src/autism_corpus
Success: no issues found in 30 source files

$ uv run autism-corpus --help
Commands: discover  fetch  parse  normalize  chunk  build  report
```

## Sample build artifacts

A real CLI build against the integration-test fixtures (5 sources, 1 document
each) produced:

| Source | Licence | Documents | Chunks |
|---|---|---:|---:|
| `cdc-autism` | public-domain | 1 | 4 |
| `nhs-autism` | OGL-UK-3.0 | 1 | 2 |
| `medlineplus-autism` | public-domain | 1 | 2 |
| `nih-nimh` | public-domain | 1 | 2 |
| `who-autism` | CC-BY-NC-SA-3.0-IGO | 1 | 1 |
| **Total** | | **5** | **11** |

Licences observed: `public-domain` (8 chunks), `OGL-UK-3.0` (2), `CC-BY-NC-SA-3.0-IGO` (1).
All three are in the recognised set documented in the PRD.

### Provenance audit (11/11 chunks sampled)

Every chunk in the sample carries:

- `chunk_id` matching `{document_id}::NNNN` (4-digit index)
- non-empty `licence`, `attribution`, `canonical_url`, `breadcrumb`, `title`
- `token_count > 0`
- `fetched_at` in ISO-8601 UTC

No chunk had HTML cruft or unattributed text. The integration test asserts
these invariants programmatically (`tests/integration/test_build_end_to_end.py`).

## Reproducibility

`tests/unit/test_pipeline.py::TestRunBuild::test_reproducible` runs `run_build`
twice on identical inputs, diffs `chunks.jsonl` ignoring `fetched_at`, and
asserts the diff is empty. Green at HEAD.

## Known limitations carried into v1.0

These are documented in code and/or the operator runbook and are NOT bugs:

1. **PMC OA bulk download is not wired into the CLI.** `adapters/pmc_oa.py`
   ships with the JATS XML logic and a `FileListEntry`-keyed discover/parse,
   but `file_list_source` and `article_loader` must be supplied by the
   operator. Run via the Python API per `docs/operator-runbook.md`.
2. **`--offline` is informational.** True offline mode requires a
   pre-populated cache; the flag warns and proceeds.
3. **robots.txt is conservative.** stdlib's `RobotFileParser` uses
   first-match-wins, not RFC 9309 longest-match. When sites list
   `Disallow:` before a matching `Allow:`, the disallow wins. Safer
   default for a polite crawler; documented in `utils/robots.py`.
4. **Short heading-bounded sections produce small chunks.** The chunker
   never splits across `#`/`##` headings, so a 40-token section becomes a
   40-token chunk. The document-level token filter (200-token minimum) is
   separate from chunk-level token bands. Acceptable for retrieval.
5. **Per-article licence mapping is pattern-based.** `pmc_oa.py` maps a
   handful of known CC labels (CC0, CC BY, CC BY-SA, CC BY-ND); novel
   labels return `None` and the article is skipped via `PmcSkip`.

## What the operator should do next

1. Run a real `autism-corpus build --all` against live sources after
   reviewing `data/seed_urls.yaml` (currently populated with the example
   URLs supplied during development — replace with real production seeds
   before any external publication).
2. Audit `report.html` for the resulting run.
3. Add a `pmc-oa-autism` wrapper script that injects production
   `file_list_source` (NCBI `oa_file_list.csv` stream) and
   `article_loader` (S3 RODA fetcher).
4. Populate `data/excluded_urls.yaml` based on the first audit pass.
