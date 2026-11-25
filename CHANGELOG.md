# Changelog

All notable changes are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Release dates are the day the changelog entry was prepared.

## [Unreleased]

### Added
- Filter rule `SENIORITY_IN_TITLE`: a title with Senior, Sr., Staff Engineer, Principal, Director, VP or Head of is rejected; Lead, Architect or Manager only need a check. Matching is by whole word, on the title only.

- Two optional profile fields, `student_status` (`graduated` | `enrolled`) and `graduation_year`.
  Profiles without them behave exactly as before.
- Filter rule `STUDENT_STATUS_REQUIRED`: with `student_status: graduated`, a posting that requires current enrollment ("currently pursuing a degree", "must be a student", "returning to school") is rejected. Wording that also welcomes graduates ("or recent graduates", "or equivalent experience") is not.
- Filter rule `GRADUATION_YEAR_MISMATCH`: with `graduation_year` set, a posting that asks for another graduation year ("graduating in 2027", "class of 2028", a range) is rejected; a range or "or later" that includes your year passes. Soft or conflicting wording gives `GRADUATION_AMBIGUOUS` (check).

### Changed
- Senior-role limitation in the README rewritten for the new rule.
- The student / graduation-year limitation in the README now describes the new rules; `profile.example.yaml` sets both fields for its fictional graduate.

## [0.1.0] - 2026-11-25

### Known limitations
- The evaluation labels are AI-suggested and not human-verified, so no accuracy claim is made; there is no student / graduation-year rule; senior titles lose level points but get no penalty or check.

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
