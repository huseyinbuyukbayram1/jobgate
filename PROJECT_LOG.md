# Project log

Newest entry first.

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
