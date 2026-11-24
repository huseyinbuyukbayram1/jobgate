# jobgate

> **Status: early development (Phase 3 - CLI and reports).** The full pipeline runs from the
> command line. Install notes, example output and limitations are still to come.

jobgate is an open-source job search helper for new graduates. It pulls publicly
available postings from ATS job boards, screens out application blockers up front
(visa, citizenship, video requirements, years of experience, language, location),
and scores what is left against your CV profile, with a reason for every number.

**It never applies for you.** There is no auto-apply and there will not be one. You
read the shortlist and submit applications yourself.

## Planned pipeline

1. **Fetch** public postings from Greenhouse, Lever and Ashby (no login, no HTML scraping).
2. **Normalize** every posting into a single `Job` schema.
3. **Filter** with rule-based blockers; every decision carries a reason code.
4. **Score** 0-100 with an explainable breakdown driven by YAML weights.
5. **Store and report** in SQLite, with Markdown and CSV reports.

Decisions are always rule-based. An optional local LLM (Ollama) may only reword the
explanation text; it never changes a filter decision or a score.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install   # enables the secret scan (gitleaks) and ruff on every commit
pytest
ruff check . && ruff format --check .
```

## Quick look (development install)

```bash
cp profile.example.yaml profile.yaml        # edit: where you may work, languages, years
cp companies.example.yaml companies.yaml    # edit: which company boards to read
jobgate companies validate
jobgate run                                 # fetch -> filter -> score -> report
# reports/report.md and reports/report.csv; `jobgate --help` lists every command
jobgate mark <id> applied                   # id is shown in the report
```

## Profile

Copy `profile.example.yaml` (a fictional person) to `profile.yaml` and edit it. It tells the
filter where you may work, which languages you speak, how many years of experience is too
much, and whether video or take-home requirements should be rejected.

## Privacy

Personal files (`profile.yaml`, `*.db`, `.env`, `cv/`) are git-ignored. Only
`*.example.*` files live in the repository, and the example profile belongs to a
fictional person.

## How this project is built

This project is developed with AI assistance: the code is written with
[Claude Code](https://claude.com/claude-code). The design decisions, the rules and the
test labelling are done by the repository owner.

## Data sources and terms

Only public, unauthenticated job-board endpoints are used; see [docs/sources.md](docs/sources.md)
for the verified endpoint shapes, politeness rules and known differences from the docs.

| ATS | Official API documentation |
|-----|----------------------------|
| Greenhouse | <https://docs.greenhouse.io/job-board.html> |
| Lever | <https://github.com/lever/postings-api> |
| Ashby | <https://developers.ashbyhq.com/docs/public-job-posting-api> |

The documentation pages above do not link a separate terms-of-use page for these
public endpoints, so none is listed yet. Any source can be switched off from the
companies file (`sources:`) if its terms change.

## License

MIT, see [LICENSE](LICENSE).
