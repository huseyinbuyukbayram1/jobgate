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

## Stage 3 as built (Phase 2): the blocker filter

`profile.py` loads `profile.yaml` (see `profile.example.yaml`). `filters.evaluate(job, profile)`
runs seven independent rules and returns a `Decision`: a verdict (`pass`, `check`, `reject`)
plus a list of reasons, each with a stable code and the sentence that triggered it. Any
`reject` wins over `check`, which wins over `pass`.

| Rule | Reject code | Check code |
|------|-------------|------------|
| Visa / work permit | `VISA_NO_SPONSORSHIP`, `WORK_AUTH_REQUIRED` | `SPONSORSHIP_CONFLICT`, `SPONSORSHIP_LOCATION_UNKNOWN` |
| Citizenship / clearance | `CITIZENSHIP_REQUIRED`, `CLEARANCE_REQUIRED` | |
| Video / take-home | `VIDEO_REQUIRED`, `ASSIGNMENT_REQUIRED` | |
| Years of experience | `EXPERIENCE_TOO_HIGH` | `EXPERIENCE_AMBIGUOUS` |
| Location | `LOCATION_OUTSIDE_PROFILE` | `LOCATION_UNCLEAR` |
| Time zone | `TIMEZONE_OUTSIDE_PROFILE` | |
| Language | `LANGUAGE_NOT_IN_PROFILE` | |

Design choices worth explaining:

- **Sentence-level regexes, no LLM.** Each rule looks at one sentence at a time, so the
  evidence shown to the user is exactly the sentence that triggered the rule.
- **Asking is cheaper than wrongly rejecting.** Wording that could go either way
  (conflicting sponsorship statements, a bare "Remote", a region the user would work in
  but may not be authorized in) becomes `check`, not `reject`.
- **Optional wording is ignored.** Sentences with "plus", "preferred", "nice to have" do not block.
- **A "no sponsorship" sentence only blocks where the user lacks work rights.** In a country
  covered by `work_authorization.regions` it is irrelevant.

`evaluation.py` measures the filter on `tests/data/labeled_postings.csv` and writes
`docs/filter_report.md`. See `docs/labeling.md` for how labels are verified.
