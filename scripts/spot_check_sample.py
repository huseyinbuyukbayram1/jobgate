"""Draw the rows for a spot check (docs/spot_checks.md) from a jobgate database.

Usage:
    python scripts/spot_check_sample.py --db jobgate.db --seed 42 --count 10 --out sample.md

For each reason code the postings that carry it are listed in the order of their internal key,
and ``count`` of them are drawn with ``random.Random(seed).sample``. Postings where the code is
the first or the only reason are preferred, so the sample does not show rejections that another
rule had already decided. If there are fewer such postings than ``count``, the rest is filled
from the others, and those rows are flagged. The evidence sentence is printed as it is stored.

The same database and the same seed always give the same rows. A database from a later fetch
holds different postings, so it gives different rows. The database is opened read-only.
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CODES = ["STUDENT_STATUS_REQUIRED", "GRADUATION_YEAR_MISMATCH"]


@dataclass(frozen=True)
class Row:
    company: str
    title: str
    url: str
    code: str
    evidence: str
    codes: list[str]  # every reason code of the posting, in stored order
    primary: bool  # the sampled code is the first (or only) reason


def _read(db: Path) -> list[tuple[str, str, str, list[dict]]]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        cursor = conn.execute(
            "SELECT j.company, j.title, j.url, d.reasons FROM jobs j "
            "JOIN decisions d ON d.job_key = j.key ORDER BY j.key"
        )
        return [(c, t, u, json.loads(r or "[]")) for c, t, u, r in cursor]
    finally:
        conn.close()


def draw(db: Path | str, codes: list[str], count: int, seed: int) -> dict[str, list[Row]]:
    stored = _read(Path(db))
    drawn: dict[str, list[Row]] = {}
    for code in codes:
        pool: list[Row] = []
        for company, title, url, reasons in stored:
            mine = [r for r in reasons if r["code"] == code]
            if mine:
                all_codes = [r["code"] for r in reasons]
                pool.append(
                    Row(company, title, url, code, mine[0]["evidence"], all_codes,
                        all_codes[0] == code)
                )  # fmt: skip
        primary = [r for r in pool if r.primary]
        others = [r for r in pool if not r.primary]
        rng = random.Random(seed)
        picked = rng.sample(primary, min(count, len(primary)))
        if len(picked) < count:
            picked += rng.sample(others, min(count - len(picked), len(others)))
        drawn[code] = picked
    return drawn


def to_markdown(drawn: dict[str, list[Row]], seed: int) -> str:
    lines = [f"# Spot-check sample (seed {seed})", ""]
    for code, rows in drawn.items():
        lines += [f"## {code}", ""]
        for number, row in enumerate(rows, 1):
            flag = "primary" if row.primary else "other reasons too: " + ", ".join(row.codes)
            lines += [
                f"{number}. **{row.company}** | {row.title} | `{code}` | {flag}",
                f"   - evidence: {row.evidence}",
                f"   - link: {row.url}",
            ]
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Draw rows for a jobgate spot check.")
    parser.add_argument("--db", required=True, help="jobgate SQLite database (opened read-only)")
    parser.add_argument("--codes", nargs="+", default=DEFAULT_CODES, help="reason codes to sample")
    parser.add_argument("--count", type=int, default=10, help="rows per code (default 10)")
    parser.add_argument("--seed", type=int, default=42, help="random seed (default 42)")
    parser.add_argument("--out", help="write the Markdown here instead of stdout")
    args = parser.parse_args(argv)
    if args.count < 1:
        print("error: --count must be at least 1", file=sys.stderr)
        return 2
    if not Path(args.db).is_file():
        print(f"error: database not found: {args.db}", file=sys.stderr)
        return 2
    try:
        drawn = draw(args.db, args.codes, args.count, args.seed)
    except sqlite3.Error as exc:
        print(f"error: cannot read {args.db}: {exc}", file=sys.stderr)
        return 2
    text = to_markdown(drawn, args.seed)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
