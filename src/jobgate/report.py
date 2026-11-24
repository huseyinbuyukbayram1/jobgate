"""Stage 5b: Markdown and CSV reports from stored rows.

Reports are pure functions of the stored rows (plus the date in the header), so the same
database always produces the same text.
"""

from __future__ import annotations

import csv
import io
import re
from collections import Counter
from datetime import date

from jobgate.storage import JobRow

CSV_COLUMNS = [
    "rank", "id", "score", "verdict", "company", "title", "location", "url",
    "posted_at", "status", "explanation", "reasons",
]  # fmt: skip


def _sort_key(row: JobRow) -> tuple[int, str, str, str]:
    return (-(row.score or 0), row.job.company.lower(), row.job.title.lower(), row.short_id)


def _clean(text: str) -> str:
    """One line of text that cannot break Markdown links or tables."""
    text = " ".join(text.split())
    for char in "[]|":
        text = text.replace(char, "\\" + char)
    return text.replace("<", "&lt;").replace(">", "&gt;")


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def _entry(rank: int, row: JobRow, with_reasons: bool) -> list[str]:
    job = row.job
    heading = f"### {rank}. {row.explanation or row.score} — [{_clean(job.title)}]({job.url})"
    posted = (
        f"posted {job.posted_at.date().isoformat()}" if job.posted_at else "posted date unknown"
    )
    lines = [
        heading,
        f"{_clean(job.company)} · {_clean(job.location) or 'location unknown'} · {posted} · "
        f"id `{row.short_id}` · status: {row.status}",
    ]
    if with_reasons:
        lines.append("")
        lines += [f"- {r['code']}: {_clean(r['evidence'])}" for r in row.reasons]
    return [*lines, ""]


def _ranked(rows: list[JobRow], verdict: str, min_score: int, limit: int | None) -> list[JobRow]:
    picked = [r for r in rows if r.verdict == verdict and (r.score or 0) >= min_score]
    picked.sort(key=_sort_key)
    return picked[:limit] if limit is not None else picked


def build_markdown(
    rows: list[JobRow], day: date, min_score: int = 0, limit: int | None = None
) -> str:
    visible = [r for r in rows if r.status != "dropped"]
    matches = _ranked(visible, "pass", min_score, limit)
    checks = _ranked(visible, "check", min_score, limit)
    rejected = [r for r in rows if r.verdict == "reject"]
    total_pass = sum(r.verdict == "pass" for r in visible)
    total_check = sum(r.verdict == "check" for r in visible)
    lines = [
        f"# jobgate report - {day.isoformat()}",
        "",
        f"{_plural(total_pass, 'match', 'matches')}, {total_check} to check, "
        f"{len(rejected)} rejected by the filter.",
        "",
        "Scores are 0-100 and always show where the points came from. "
        "Nothing here is applied for you.",
        "",
        "## Ranked matches",
        "",
    ]
    if matches:
        for rank, row in enumerate(matches, 1):
            lines += _entry(rank, row, with_reasons=False)
    else:
        lines += ["No matches.", ""]
    lines += ["## Needs a check", ""]
    if checks:
        for rank, row in enumerate(checks, 1):
            lines += _entry(rank, row, with_reasons=True)
    else:
        lines += ["Nothing to check.", ""]
    lines += ["## Rejected by the filter", ""]
    counts = Counter(
        reason["code"]
        for row in rejected
        for reason in row.reasons
        if reason["verdict"] == "reject"
    )
    if counts:
        lines += [
            f"- {code}: {n}" for code, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ]
    else:
        lines.append("None.")
    return "\n".join(lines).rstrip("\n") + "\n"


def build_csv(rows: list[JobRow], include_rejected: bool = False) -> str:
    visible = [r for r in rows if r.status != "dropped"]
    ranked = sorted((r for r in visible if r.verdict in ("pass", "check")), key=_sort_key)
    extra = (
        sorted((r for r in visible if r.verdict == "reject"), key=_sort_key)
        if include_rejected
        else []
    )
    ranked_ids = {r.short_id for r in ranked}
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for position, row in enumerate([*ranked, *extra], 1):
        job = row.job
        writer.writerow(
            {
                "rank": position if row.short_id in ranked_ids else "",
                "id": row.short_id,
                "score": "" if row.score is None else row.score,
                "verdict": row.verdict,
                "company": job.company,
                "title": re.sub(r"\s+", " ", job.title),
                "location": job.location,
                "url": job.url,
                "posted_at": job.posted_at.date().isoformat() if job.posted_at else "",
                "status": row.status,
                "explanation": row.explanation or "",
                "reasons": ";".join(r["code"] for r in row.reasons),
            }
        )
    return out.getvalue()
