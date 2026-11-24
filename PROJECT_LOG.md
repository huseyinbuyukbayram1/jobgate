# Project log

Newest entry first.

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
