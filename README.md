# jobgate

> **Status: early development (Phase 0 – project skeleton).** Nothing here is usable yet.

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

## Privacy

Personal files (`profile.yaml`, `*.db`, `.env`, `cv/`) are git-ignored. Only
`*.example.*` files live in the repository, and the example profile belongs to a
fictional person.

## How this project is built

This project is developed with AI assistance: the code is written with
[Claude Code](https://claude.com/claude-code). The design decisions, the rules and the
test labelling are done by the repository owner.

## Data sources and terms

Terms-of-use links for each supported ATS will be listed here once the adapters land
in Phase 1. Sources can be switched off from configuration if their terms change.

## License

MIT, see [LICENSE](LICENSE).
