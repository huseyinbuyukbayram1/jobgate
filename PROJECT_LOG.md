# Project log

## PENDING GATES (read before releasing or publishing anything)

Changed 2026-11-24 (owner decision): **`v0.1.0` may be released without label verification**, but
the tag is still only created when the owner says so explicitly.

- [ ] **No accuracy claim (still forbidden).** Until the owner has set `human_verified=true` on
  rows of `tests/data/labeled_postings.csv` and `tests/data/heldout_postings.csv` and re-run
  `python -m jobgate.evaluation`, **no accuracy number (percentage or ratio) may appear in the
  README, CHANGELOG, any X post, release notes or anywhere else public.** `tests/test_docs.py`
  enforces it for README and CHANGELOG. The README has an "Evaluation" section that says the
  labels are AI-suggested and gives the verified/total row count (currently 0 of 68); the
  evaluation report starts with the same count. Numbers inside `docs/*_report.md` and this log
  are labelled preliminary (AI-suggested labels).
- [ ] Target to lift the ban: at least 90% accuracy on human-verified rows, with the false
  rejection rate reported next to it.

Newest entry first.

## 2026-11-24 - Gate change, held-out label fixes, evaluation section

**Done**
- Gate changed by the owner: `v0.1.0` can ship unverified; accuracy claims stay forbidden. Updated here and in `CLAUDE.md`; `test_docs` no longer bans the version string but still bans accuracy numbers and now checks that the README's verified/total counts match the CSV files.
- README: new "Evaluation" section (labels AI-suggested, 0 / 40 and 0 / 28 verified, no independent verification, no accuracy claim, how to run `jobgate.evaluation`).
- Evaluation report now opens with "Human-verified rows: X of Y".
- Held-out labels: H006 and H009 -> `uncertain`; H022 `suggested_reason` -> `LOCATION_OUTSIDE_PROFILE`. `human_verified` stays false. Reports regenerated: the held-out set now shows two more preliminary mismatches (H006, H009: the filter passes them), because the labels moved, not the filter.
- Issue draft for a student / graduation-year rule: `docs/issue_drafts/graduation-year-rule.md` (not implemented).

## 2026-11-24 - Phase 4: optional LLM rationale, README, CHANGELOG

**Done**
- CI fix first: `test_help_has_no_double_negative_flags` failed in CI because Rich coloured and wrapped `--help`. Reproduced locally with `FORCE_COLOR=1 COLUMNS=60`; the CLI tests now run with `NO_COLOR`, `TERM=dumb`, wide columns and strip ANSI codes (commit `deefe28`, CI green).
- `llm.py` + `llm.example.yaml`: optional rationale. Off by default (`llm.yaml` is git-ignored). `OllamaClient` (`POST /api/chat`, `stream:false`, checked against Ollama's docs via Context7), `OpenAICompatibleClient` (optional key from a named environment variable). Only title, company, location and the score breakdown are sent.
- The rationale is stored in its own `decisions.rationale` column (older databases get the column on open), shown as a `>` line in the report and as a CSV column. It is cleared only when the score explanation changes, so a second run makes no new LLM calls.
- If the LLM is unreachable: one warning, one `LLM unavailable (...)` line, the run continues. `jobgate explain` is a new command; `run` calls it only when enabled.
- README rewritten (problem, 10-minute setup, example output, mermaid diagram, optional LLM, what it does not do, limitations, roadmap, AI-assisted disclosure, ATS docs table with terms marked "to be verified"), CHANGELOG (Unreleased only), architecture doc with the LLM diagram.
- `tests/test_docs.py` guards the gate: README and CHANGELOG contain no accuracy percentage and no version tag, the profile snippet in the README is a valid profile, and every command the README shows exists.
- 261 tests, ruff clean.

**Gate: met.** In a clean `git clone` + new venv: `pip install -e .` 7 s, `jobgate companies validate`, `jobgate run` ~48 s live (10 companies, 2,645 postings) with a ranked `report.md`; about a minute of work in total. With `llm.yaml` enabled and no Ollama installed, `jobgate explain` and `jobgate run` exit 0 with the warning.

**Problems and fixes**
- Name clash: `cli.make_client` (HTTP) vs `llm.make_client`; imported the LLM one as `build_llm_client` and exposed `make_llm_client` for tests to replace.
- My first README profile snippet did not match the real profile schema; replaced it with an excerpt and added a test that loads it.

**Assumptions / limits**
- Ollama is not installed on this machine, and no cloud key was used: both LLM clients are tested only with fake servers. The unreachable-server path was run for real.
- Terms-of-use links for the three ATS vendors are still unverified; the README says "to be verified".
- Still open: the label-verification gate above (no accuracy number, no `v0.1.0` tag).

**Next:** wait for the owner to verify labels and re-run the evaluation; then decide on a release.

## 2026-11-24 - Phase 3: scoring, SQLite, CLI, reports (+ held-out batch)

**Done**
- Pending label-verification gate written at the top of this file and in `CLAUDE.md`.
- Held-out batch `tests/data/heldout_postings.csv`: 28 real junior/new-grad software, AI and data engineering postings from 23 companies the first set never used (short quotes + source links, suggested labels, `human_verified=false`). Labels were committed *before* the filter was run on it; the filter was not changed afterwards. First-run result (preliminary, unverified labels) is in `docs/heldout_report.md`. Findings: 2 safe-direction misses (Cloudflare `In-Office` rows, city only in the text) and 1 row rejected for the wrong reason (video-prompt wording not recognised). Not fixed on purpose. The batch has no `uncertain` rows.
- `scoring.py` + `scoring.example.yaml`: five integer parts that add up to the total; weights in YAML, must sum to 100; profile gained a `preferences` section (target/avoid roles, technologies, work modes).
- `storage.py`: SQLite (`jobs`, `decisions`, `status_history`, `runs`), upserts keyed by `Job.key`, closed postings marked inactive only for companies fetched successfully.
- `report.py`: ranked Markdown + CSV, deterministic output.
- `cli.py` (typer): `fetch | filter | score | report | mark | run | companies validate`, English help and errors, exit codes 0/1/2. Console script `jobgate`.
- `experience_mentions()` extracted from the experience rule so the scorer reads the same numbers (behaviour unchanged: both labelled-set results identical before and after).
- 222 tests, ruff clean.

**Gate: met.** One command (`jobgate run`) on the 10 example companies, live network, ~27 s: 2,645 postings, 52 pass, 235 check, 2,358 reject, 287 scored, ranked `report.md` + `report.csv`. Second run: 0 new rows, `jobs`/`decisions`/`status_history` row counts unchanged, both report files byte-identical (only the `runs` log grows, by design).

**Problems and fixes**
- Typer printed `--no-no-cache` for a boolean named `no_cache`; fixed with `--cache/--no-cache` and a test.
- A `sed` command failed on macOS and silently skipped the rest of a `&&` chain; caught because the next test run did not show the expected change.

**Assumptions / limits**
- Scoring is keyword based: "Technical Support Engineer" earns half the role points for the target "software engineer" because "engineer" matches. Reasonable to tighten in a later phase.
- Many Cloudflare postings only say `Hybrid` or `In-Office` as location, so they land in "check".
- Python 3.12/3.13 (the CI versions) are not installed on this machine; only 3.14 was run locally. CI is the first real check for 3.12/3.13.
- `mark` statuses: `found` (automatic), `applied`, `dropped`.

**Next (Phase 4)**
- Ollama rationale text (LLM only rewords, off by default, a test proves everything works with it off), README (problem, 10-minute setup, example output, mermaid diagram, limitations, what it does not do, roadmap), CHANGELOG. The accuracy gate above still blocks `v0.1.0` and any public accuracy number.

## 2026-11-24 - Phase 2: profile, blocker filter, labelled set, accuracy report

**Done**
- `profile.py` + `profile.example.yaml` (fictional person; no name, no e-mail): work-authorization regions, citizenships, clearance, max years of experience, languages, allowed locations, time zones, video/take-home settings.
- `filters.py`: seven rules (visa, citizenship/clearance, video/take-home, experience, location, time zone, language). Every reason has a code and the triggering sentence; reject > check > pass.
- 40-row labelled set (`tests/data/labeled_postings.csv`): 20 blocked, 13 clear, 7 uncertain; 28 short real quotes with source links, 12 synthetic. All `human_verified=false`.
- `evaluation.py` + `docs/filter_report.md`; `docs/labeling.md` explains how the owner verifies labels.
- 149 tests, ruff clean.

**Gate status: partially met, by design**
- Human-verified rows: 0 of 40, so the real >= 90% target cannot be claimed yet. The report says so explicitly.
- Preliminary (unverified labels): 39 of 40 correct, 0 of 20 non-blocked rejected, 0 of 20 blocked passed unflagged. The one miss is a posting whose location field is only "Hybrid"; the filter says "check" instead of "reject" (the safe direction). These numbers are optimistic because I tuned the filter while looking at these rows.

**Problems and fixes (found by running the filter on real postings)**
- "without sponsorship for an export license" (Cloudflare boilerplate on hundreds of postings) was read as a visa blocker. Sentences about export control, employer-sponsored benefits and executive sponsors are now ignored.
- "speak English and Spanish fluently" was missed because "fluently" did not match; now `fluen\w+`.
- "In-Office" as a location counted as outside the profile; workplace-mode words alone are now "unclear" (check).
- "Remote - Europe" plus "no sponsorship" used to be rejected; now it is a check, because Europe is somewhere the user would work but does not prove their right to work there.
- A conflicting sponsorship statement is harmless where the user may work; it no longer raises a check there.
- I accidentally put the employer name into a test assertion; caught by the final grep, removed, and the unpushed commits were rewritten so it is not in history.

**Assumptions**
- Labels judged against the example profile (Germany/EU work rights, English + German, max 2 years).
- Years rule uses the lower bound of a range ("2-5 years" asks 2); the threshold is the profile's `max_experience_years`.
- Location is matched as whole words against the posting's location field only.

**Next**
- Owner: verify labels in the CSV (`docs/labeling.md`), then run `python -m jobgate.evaluation --out docs/filter_report.md`.
- Phase 3: scoring with YAML weights, SQLite storage, CLI commands, Markdown/CSV report, idempotent re-runs.

## 2026-11-24 - Phase 1: Job schema, adapters, HTTP layer, companies reader

**Done**
- `Job` schema (pydantic v2) with a stable `key` for de-duplication; `workplace_type` added as an optional field because scoring needs work mode later.
- Endpoints verified by hand (curl, 3+ companies per ATS) and against official docs; differences recorded in `docs/sources.md`.
- `HttpClient`: explicit User-Agent, 1 s throttle, timeout, max 3 retries with exponential backoff, daily on-disk cache (`.jobgate_cache/`, git-ignored).
- Greenhouse, Lever and Ashby adapters, each with a pure `parse` tested on synthetic fixtures (no network in tests).
- `companies.py` reader/validator with per-source on/off switches; `companies.example.yaml` with 10 neutral public companies.
- `fetch_all`: a failing company is recorded and the run continues.
- 51 tests, ruff clean.

**Gate result (real network, 30 companies)**: 27 fetched, 3 failed, run continued, 5,793 postings (Greenhouse 3,696, Lever 757, Ashby 1,340). The 3 failures: one board I broke on purpose, two stale tokens (HTTP 404). Every posting had a description, location and date. The 30-company list lives outside the repo (scratchpad), not committed.

**Problems and fixes**
- Docs vs. live differences: Greenhouse list has `first_published`, Lever has `createdAt`, Ashby has `id`, none documented. Adapters use them but fall back to documented fields.
- Lever pagination is undocumented; checked live that the default returns everything (Palantir 305 postings, `skip=305` returned 0).
- No terms-of-use link found in any of the three API docs; none claimed in README. Needs the owner's confirmation.

**Assumptions**
- Lever EU hosting (`api.eu.lever.co`) not supported yet.
- Unlisted Ashby jobs (`isListed: false`) are skipped.
- Cache is per calendar day (local date), matching "do not hit the same endpoint twice in one night".

**Next**
- Phase 2: profile schema and example, blocker filter rules with reason codes, labelled set (CSV of candidates for the owner to verify), accuracy report.

## 2026-11-24 - Phase 0: skeleton, CI, secret scan

**Done**
- Committed the existing package skeleton (`pyproject.toml`, `src/jobgate`, smoke tests) in small commits.
- Added `CLAUDE.md` (project rules), `docs/` (architecture and sources skeletons) and a README skeleton that states the AI-assisted workflow.
- Added GitHub Actions CI: ruff (lint and format check) and pytest on Python 3.12 and 3.13, plus a gitleaks secret-scan job.
- Added pre-commit with gitleaks and ruff hooks.

**Assumptions and decisions**
- The local `.venv` pointed at a path that no longer existed, so it was recreated (it is git-ignored). It runs Python 3.14; the package targets `>=3.12` and CI covers 3.12 and 3.13.
- Dependencies (httpx, pydantic, typer, PyYAML) are added in the phase that first needs them, not up front.
- The employer-name line in the pasted `CLAUDE.md` was reworded so the public file does not contain that name itself.
- Hook revisions were checked against upstream tags: gitleaks `v8.30.1`, ruff-pre-commit `v0.17.6`.
- Nothing has been pushed; CI has therefore not run on GitHub yet.

**Next**
- Phase 1: `Job` schema, Greenhouse/Lever/Ashby adapters, cache, retry and delay, companies reader (10 example companies). Endpoint shapes get verified by hand against 3 real companies per ATS first.
