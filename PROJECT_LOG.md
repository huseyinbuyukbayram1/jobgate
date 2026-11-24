# Project log

## PENDING GATES (read before releasing or publishing anything)

- [ ] **Label verification (owner).** Until the owner has set `human_verified=true` on the rows of
  `tests/data/labeled_postings.csv` (and on the held-out batch `tests/data/heldout_postings.csv`) and
  re-run `python -m jobgate.evaluation`, **no accuracy number may be written in the README, in any
  X post, in release notes, or anywhere else public.** The same gate blocks the `v0.1.0` tag.
  Numbers that already exist in `docs/filter_report.md` and in this log are labelled preliminary:
  they use AI-suggested labels and the filter was tuned on those rows.
- [ ] Target to clear the gate: at least 90% accuracy on human-verified rows, with the false
  rejection rate reported next to it.

Newest entry first.

## 2026-11-24 - Phase 2: profile, blocker filter, labelled set, accuracy report

**Done**
- `profile.py` + `profile.example.yaml` (fictional person; no name, no e-mail): work-authorization regions, citizenships, clearance, max years of experience, languages, allowed locations, time zones, video/take-home settings.
- `filters.py`: seven rules (visa, citizenship/clearance, video/take-home, experience, location, time zone, language). Every reason has a code and the triggering sentence; reject > check > pass.
- 40-row labelled set (`tests/data/labeled_postings.csv`): 20 blocked, 13 clear, 7 uncertain; 28 short real quotes with source links, 12 synthetic. All `human_verified=false`.
- `evaluation.py` + `docs/filter_report.md`; `docs/labeling.md` explains how the owner verifies labels.
- 149 tests, ruff clean.

**Gate status: partially met, by design**
- Human-verified rows: 0 of 40, so the real >= 90% target cannot be claimed yet. The report says so explicitly.
- Preliminary (unverified labels): accuracy 97.5% (39/40), false rejection rate 0.0% (0/20), missed-block rate 0.0% (0/20). The one miss is a posting whose location field is only "Hybrid"; the filter says "check" instead of "reject" (the safe direction). These numbers are optimistic because I tuned the filter while looking at these rows.

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
