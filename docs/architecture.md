# Architecture

Status: skeleton (Phase 0). Filled in as each stage is built.

jobgate is a five-stage pipeline. Each stage is independently testable and talks to
the next one through plain, typed data.

| # | Stage | Input | Output |
|---|-------|-------|--------|
| 1 | Fetch | company list (YAML) | raw ATS JSON, cached locally |
| 2 | Normalize | raw JSON | `Job` objects |
| 3 | Filter | `Job` + profile | pass / reject / check, with a reason code |
| 4 | Score | passed `Job` + profile + weights | 0-100 score with breakdown |
| 5 | Store + Report | scored jobs | SQLite rows, Markdown and CSV reports |

Core rule: every decision is rule-based. The optional LLM only rewords explanation
text and never influences a filter result or a score.

## Stage 1-2 as built (Phase 1)

- `http.py` - `HttpClient.get_json`: User-Agent, throttle, timeout, retries, daily cache.
- `adapters/base.py` - `Adapter` with `request(token)`, pure `parse(raw, company)` and `fetch(...)`. One malformed posting is skipped, a wrong overall shape raises `FetchError`.
- `adapters/{greenhouse,lever,ashby}.py` - one small class each; `parse` is tested on fixtures.
- `models.py` - the single `Job` schema; `Job.key` (`ats:company:id`) is the de-duplication identity.
- `companies.py` - YAML reader with validation and per-source on/off switches.
- `fetch.py` - `fetch_all` runs every active company; a failure is recorded in the report and the run continues.
