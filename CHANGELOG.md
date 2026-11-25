# Changelog

All notable changes are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Release dates are the day the changelog entry was prepared.

## [Unreleased]

### Added
- Role matching reads the title more carefully (still rule-based and explainable): the title is normalised, `role_synonyms` in `scoring.example.yaml` (also the built-in default) map titles such as "member of technical staff", "developer" or "swe" to "software engineer", and a whole target phrase scores higher than scattered words, a phrase only in a later part of the title, or a partial match. The report names the match that counted (`role match: ...`, and a `role_match` CSV column); the database gets a `role_match` column (older databases are upgraded on open). Weights still add up to 100 and no filter verdict changes.

- `scripts/spot_check_sample.py`: draws the rows of a spot check from a jobgate database with a seed (read-only, same database and seed give the same rows); `docs/spot_checks.md` refers to it.
- Lever EU host: a Lever company can set `region: eu` in `companies.yaml` to be fetched from `api.eu.lever.co` (same path and parameters). Covered by fixture tests only; never tried with a real EU-hosted board. `region` is rejected on other sources, and the same site name may appear once per region.
- `jobgate --version` prints the installed version (`jobgate 0.2.0`) and exits.
- `jobgate check [FILE] [--title TEXT] [--location TEXT]`: run the filter rules on one pasted posting (a file, or stdin) and print the verdict with each reason code and its sentence. No network, no database, no LLM. Without `--location` the location rule is skipped and the output says so.

### Changed
- Partial role matches only count words in the first part of the title, not in a team name after a dash, comma or bracket, so "Systems Engineer (Data Intelligence Team)" no longer counts as a data engineer; "Engineering Manager" is no longer read as an engineer title.

## [0.2.0] - 2026-11-25

### Known limitations
- The evaluation labels are AI-suggested and not human-verified, so no accuracy claim is made. The spot check in `docs/spot_checks.md` was read by the AI assistant only, not yet by the repository owner.
- Role matching is keyword-based. A title worded differently from your `target_roles` gets 0 role points, so some technical titles (for example "Security Research Analyst" or "Member of Technical Staff") land in **Low role match**.
- With the example profile, **Ranked matches** can be empty: in the example run every posting that passed the filter had 0 role points, and the engineering postings were in **Needs a check** or **Low role match**.
- Graduation windows are checked by year only (no months), and a season such as "Summer 2027" is not read as a graduation year.

### Added
- Filter rule `SENIORITY_IN_TITLE`: a title with Senior, Sr., Staff Engineer, Principal, Director, VP or Head of is rejected; Lead, Architect or Manager only need a check. Matching is by whole word, on the title only.
- Two optional profile fields, `student_status` (`graduated` | `enrolled`) and `graduation_year`.
  Profiles without them behave exactly as before.
- Filter rule `STUDENT_STATUS_REQUIRED`: with `student_status: graduated`, a posting that requires current enrollment ("currently pursuing a degree", "must be a student", "returning to school") is rejected. Wording that also welcomes graduates ("or recent graduates", "or equivalent experience") is not.
- Filter rule `GRADUATION_YEAR_MISMATCH`: with `graduation_year` set, a posting that asks for another graduation year ("graduating in 2027", "class of 2028", a range) is rejected; a range or "or later" that includes your year passes. Soft or conflicting wording gives `GRADUATION_AMBIGUOUS` (check).
- Report: a posting that passed the filter, or needs a check, with role score 0 is listed under a new **Low role match** section (Markdown) instead of **Ranked matches** or **Needs a check**, with its score, breakdown and (for a check) the filter's reasons. The CSV gains `section` and `role_points` columns, and `jobgate run` prints how many postings were set apart. Scores, weights, filter rules and verdicts are unchanged.
- Label schema: `SENIORITY_IN_TITLE` is a blocker category in `docs/labeling.md`, a label cell may list several acceptable reason codes separated by `|`, and the suggested labels of ten development-set rows were updated (recorded under "Label changes"). They are still AI suggestions, not human-verified.
- `docs/spot_checks.md`: a small, narrow spot check of rejections by the student-status and graduation-year rules, with its limits. It is not an accuracy claim.

### Changed
- The `User-Agent` version is now taken from the package version (`jobgate.__version__`) instead of a hard-coded string, so it reads `jobgate/0.2.0`.
- README limitations and roadmap updated for the seniority, student-status, graduation-year and role-matching changes; `profile.example.yaml` sets both new profile fields for its fictional graduate.

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
