# Changelog

All notable changes are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Nothing has been released yet:
everything below is under **Unreleased** until the project owner decides to cut a release.

## Unreleased

### Added
- Fetch public postings from Greenhouse, Lever and Ashby with an explicit User-Agent, request
  delay, timeout, up to 3 retries with back-off and a daily on-disk cache. A failing company
  is recorded and the run continues.
- A single `Job` schema and a companies file with per-source on/off switches.
- Rule-based blocker filter (visa and work authorization, citizenship and clearance, video and
  take-home requirements, years of experience, language, location, time zone) driven by
  `profile.yaml`. Every decision is `pass`, `check` or `reject` with a reason code and the
  sentence behind it.
- Hand-collected evaluation sets with suggested labels, an evaluation report, and a held-out
  set that the filter was not tuned on. Labels are not yet human-verified.
- Explainable 0-100 score (role, technology, level, location, compensation) with weights in YAML.
- SQLite storage with idempotent upserts, status history (found / applied / dropped) and
  postings that disappear from a board marked inactive.
- Deterministic Markdown and CSV reports.
- Command line: `fetch`, `filter`, `score`, `explain`, `report`, `mark`, `run`,
  `companies validate`.
- Optional LLM rationale (Ollama, or an OpenAI-compatible API through config). Off by default;
  it only adds wording, never changes a verdict or score, and jobgate carries on with the
  rule-based explanation when the LLM is off or unreachable.
- README with setup, example output, architecture diagram, limitations and roadmap; CI (ruff,
  pytest on Python 3.12 and 3.13, secret scan) and a pre-commit secret scan.

### Documentation
- Terms-of-use links per ATS (customer terms, with a note that no separate API terms were found) and a "Responsible use" section.

### Fixed
- CLI help tests no longer depend on terminal colour or width.
