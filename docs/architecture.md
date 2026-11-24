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
