"""Stage 5b: Markdown and CSV reports from stored rows.

Reports are pure functions of the stored rows (plus the date in the header), so the same
database always produces the same text.

A posting that passed the filter (or needs a check) but whose title earned 0 role points (for
example a sales role for a software-engineering profile) is not listed under "Ranked matches"
or "Needs a check". It still has its score and breakdown, and is shown under "Low role match"
instead, with the filter's reasons when it needs a check. Only the report changes: no verdict,
weight or stored score is touched.
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
    "posted_at", "status", "explanation", "rationale", "reasons", "section", "role_points",
    "role_match",
]  # fmt: skip


def _sort_key(row: JobRow) -> tuple[int, str, str, str]:
    return (-(row.score or 0), row.job.company.lower(), row.job.title.lower(), row.short_id)


def is_low_role(row: JobRow) -> bool:
    """A passing or to-check posting whose stored role points are 0. No breakdown: not low."""
    return row.verdict in ("pass", "check") and row.parts.get("role") == 0


def _breakdown(row: JobRow) -> str:
    """Like ``explanation`` but with the role part always shown, even when it is 0."""
    if not row.parts:
        return str(row.explanation or row.score)
    shown = ", ".join(f"{name} {pts}" for name, pts in row.parts.items() if pts or name == "role")
    return f"{row.score}: {shown}"


def _clean(text: str) -> str:
    """One line of text that cannot break Markdown links or tables."""
    text = " ".join(text.split())
    for char in "[]|":
        text = text.replace(char, "\\" + char)
    return text.replace("<", "&lt;").replace(">", "&gt;")


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def _entry(rank: int, row: JobRow, with_reasons: bool, low_role: bool = False) -> list[str]:
    job = row.job
    text = _breakdown(row) if low_role else (row.explanation or row.score)
    heading = f"### {rank}. {text} — [{_clean(job.title)}]({job.url})"
    posted = (
        f"posted {job.posted_at.date().isoformat()}" if job.posted_at else "posted date unknown"
    )
    lines = [
        heading,
        f"{_clean(job.company)} · {_clean(job.location) or 'location unknown'} · {posted} · "
        f"id `{row.short_id}` · status: {row.status}"
        + (f" · role match: {_clean(row.role_match)}" if row.role_match else ""),
    ]
    if row.rationale:
        lines += ["", f"> {_clean(row.rationale)}"]
    if with_reasons:
        lines.append("")
        lines += [f"- {r['code']}: {_clean(r['evidence'])}" for r in row.reasons]
    return [*lines, ""]


def _ranked(
    rows: list[JobRow], verdict: str | None, min_score: int, limit: int | None, low_role: bool
) -> list[JobRow]:
    """Rows of one verdict (``None``: pass and check) that are or are not low role."""
    picked = [
        r
        for r in rows
        if (r.verdict == verdict if verdict else r.verdict in ("pass", "check"))
        and (r.score or 0) >= min_score
        and is_low_role(r) == low_role
    ]
    picked.sort(key=_sort_key)
    return picked[:limit] if limit is not None else picked


def build_markdown(
    rows: list[JobRow], day: date, min_score: int = 0, limit: int | None = None
) -> str:
    visible = [r for r in rows if r.status != "dropped"]
    matches = _ranked(visible, "pass", min_score, limit, low_role=False)
    low_matches = _ranked(visible, None, min_score, limit, low_role=True)
    checks = _ranked(visible, "check", min_score, limit, low_role=False)
    rejected = [r for r in rows if r.verdict == "reject"]
    total_low = sum(is_low_role(r) for r in visible)
    total_pass = sum(r.verdict == "pass" and not is_low_role(r) for r in visible)
    total_check = sum(r.verdict == "check" for r in visible) - sum(
        r.verdict == "check" and is_low_role(r) for r in visible
    )
    lines = [
        f"# jobgate report - {day.isoformat()}",
        "",
        f"{_plural(total_pass, 'match', 'matches')}, {total_low} low role match, "
        f"{total_check} to check, {len(rejected)} rejected by the filter.",
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
    lines += [
        "## Low role match",
        "",
        "Nothing in the title of these postings matches your target roles (role 0). They "
        "keep their score and are listed here instead of under Ranked matches or Needs a "
        "check; a posting the filter was unsure about shows its reasons.",
        "",
    ]
    if low_matches:
        for rank, row in enumerate(low_matches, 1):
            lines += _entry(rank, row, with_reasons=row.verdict == "check", low_role=True)
    else:
        lines += ["None.", ""]
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
    scored = [r for r in visible if r.verdict in ("pass", "check")]
    ranked = sorted((r for r in scored if not is_low_role(r)), key=_sort_key)
    low_role = sorted((r for r in scored if is_low_role(r)), key=_sort_key)
    extra = (
        sorted((r for r in visible if r.verdict == "reject"), key=_sort_key)
        if include_rejected
        else []
    )
    ranked_ids = {r.short_id for r in ranked}
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for position, row in enumerate([*ranked, *low_role, *extra], 1):
        job = row.job
        if is_low_role(row):
            section = "low_role_match"
        else:
            section = {"pass": "ranked", "check": "check"}.get(row.verdict or "", "rejected")
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
                "rationale": row.rationale or "",
                "reasons": ";".join(r["code"] for r in row.reasons),
                "section": section,
                "role_points": row.parts["role"] if "role" in row.parts else "",
                "role_match": row.role_match or "",
            }
        )
    return out.getvalue()
