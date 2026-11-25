"""Stage 5a: SQLite storage (stdlib sqlite3).

Everything is keyed by ``Job.key`` so running any command twice never duplicates a row:
jobs and decisions are upserted, and the status history only grows when a status really
changes. The database file holds personal job-search state and is git-ignored (``*.db``).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from jobgate.filters import Reason, Verdict
from jobgate.models import Job

STATUSES = ("found", "applied", "dropped")

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    key TEXT PRIMARY KEY,
    short_id TEXT NOT NULL,
    company TEXT NOT NULL,
    ats TEXT NOT NULL,
    ats_job_id TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT NOT NULL,
    description TEXT NOT NULL,
    url TEXT NOT NULL,
    posted_at TEXT,
    workplace_type TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS jobs_short_id ON jobs (short_id);
CREATE TABLE IF NOT EXISTS decisions (
    job_key TEXT PRIMARY KEY REFERENCES jobs (key),
    verdict TEXT NOT NULL,
    reasons TEXT NOT NULL,
    score INTEGER,
    breakdown TEXT,
    explanation TEXT,
    rationale TEXT,
    role_match TEXT
);
CREATE TABLE IF NOT EXISTS status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_key TEXT NOT NULL REFERENCES jobs (key),
    status TEXT NOT NULL,
    noted_at TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL,
    jobs_seen INTEGER NOT NULL,
    new_jobs INTEGER NOT NULL,
    failures TEXT NOT NULL
);
"""


class StorageError(Exception):
    """A storage operation was given something it cannot act on."""


def short_id(key: str) -> str:
    return hashlib.sha1(key.encode(), usedforsecurity=False).hexdigest()[:8]


@dataclass
class JobRow:
    """A stored job joined with its latest decision, score and status."""

    job: Job
    short_id: str
    first_seen: str
    last_seen: str
    active: bool
    status: str
    verdict: str | None = None
    reasons: list[dict[str, str]] = field(default_factory=list)
    score: int | None = None
    parts: dict[str, int] = field(default_factory=dict)
    explanation: str | None = None
    rationale: str | None = None
    role_match: str | None = None


class Storage:
    def __init__(self, path: Path | str) -> None:
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        columns = {r["name"] for r in self.conn.execute("PRAGMA table_info(decisions)")}
        if "rationale" not in columns:  # database created before the optional LLM layer
            self.conn.execute("ALTER TABLE decisions ADD COLUMN rationale TEXT")
        if "role_match" not in columns:  # database created before role-match explanations
            self.conn.execute("ALTER TABLE decisions ADD COLUMN role_match TEXT")

    def __enter__(self) -> Storage:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self.conn.commit()
        self.conn.close()

    # -- jobs ------------------------------------------------------------------------

    def upsert_jobs(self, jobs: Iterable[Job], day: date) -> int:
        """Insert new jobs and refresh known ones. Returns how many were new."""
        new = 0
        today = day.isoformat()
        with self.conn:
            for job in jobs:
                values = (
                    job.company, job.ats, job.ats_job_id, job.title, job.location,
                    job.description, job.url,
                    job.posted_at.isoformat() if job.posted_at else None,
                    job.workplace_type,
                )  # fmt: skip
                exists = self.conn.execute(
                    "SELECT 1 FROM jobs WHERE key = ?", (job.key,)
                ).fetchone()
                if exists:
                    self.conn.execute(
                        "UPDATE jobs SET company=?, ats=?, ats_job_id=?, title=?, location=?, "
                        "description=?, url=?, posted_at=?, workplace_type=?, last_seen=?, "
                        "active=1 WHERE key=?",
                        (*values, today, job.key),
                    )
                else:
                    new += 1
                    self.conn.execute(
                        "INSERT INTO jobs (key, short_id, company, ats, ats_job_id, title, "
                        "location, description, url, posted_at, workplace_type, first_seen, "
                        "last_seen) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (job.key, short_id(job.key), *values, today, today),
                    )
                    self._add_history(job.key, "found", "first seen")
        return new

    def deactivate_missing(
        self, fetched_ok: set[tuple[str, str]], seen_keys: set[str], day: date
    ) -> int:
        """Mark postings gone from companies that were fetched successfully this run."""
        closed = 0
        with self.conn:
            for row in self.conn.execute("SELECT key, ats, company FROM jobs WHERE active = 1"):
                if (row["ats"], row["company"]) in fetched_ok and row["key"] not in seen_keys:
                    self.conn.execute("UPDATE jobs SET active = 0 WHERE key = ?", (row["key"],))
                    closed += 1
        return closed

    def record_run(self, day: date, jobs_seen: int, new_jobs: int, failures: list[str]) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO runs (run_date, jobs_seen, new_jobs, failures) VALUES (?,?,?,?)",
                (day.isoformat(), jobs_seen, new_jobs, json.dumps(failures)),
            )

    # -- decisions and scores --------------------------------------------------------

    def save_decision(self, job_key: str, verdict: Verdict, reasons: list[Reason]) -> None:
        payload = json.dumps(
            [{"code": r.code, "verdict": r.verdict.value, "evidence": r.evidence} for r in reasons]
        )
        with self.conn:
            self.conn.execute(
                "INSERT INTO decisions (job_key, verdict, reasons) VALUES (?,?,?) "
                "ON CONFLICT(job_key) DO UPDATE SET verdict=excluded.verdict, "
                "reasons=excluded.reasons",
                (job_key, verdict.value, payload),
            )
            if verdict is Verdict.REJECT:  # rejected postings are never ranked
                self.conn.execute(
                    "UPDATE decisions SET score=NULL, breakdown=NULL, explanation=NULL, "
                    "rationale=NULL, role_match=NULL "
                    "WHERE job_key=?",
                    (job_key,),
                )

    def save_score(
        self,
        job_key: str,
        total: int,
        parts: dict[str, int],
        explanation: str,
        role_match: str = "",
    ) -> None:
        with self.conn:
            cursor = self.conn.execute(
                "UPDATE decisions SET score=?, breakdown=?, "
                "rationale=CASE WHEN explanation IS ? THEN rationale ELSE NULL END, "
                "explanation=?, role_match=? WHERE job_key=?",
                (total, json.dumps(parts), explanation, explanation, role_match or None, job_key),
            )
        if cursor.rowcount == 0:
            raise StorageError(f"cannot score {job_key}: run the filter first")

    def save_rationale(self, job_key: str, rationale: str) -> None:
        """Store the optional LLM text. It never touches verdict, score or explanation."""
        with self.conn:
            self.conn.execute(
                "UPDATE decisions SET rationale=? WHERE job_key=?", (rationale, job_key)
            )

    # -- status ----------------------------------------------------------------------

    def _add_history(self, job_key: str, status: str, note: str = "") -> None:
        self.conn.execute(
            "INSERT INTO status_history (job_key, status, noted_at, note) VALUES (?,?,?,?)",
            (job_key, status, datetime.now(UTC).isoformat(timespec="seconds"), note),
        )

    def resolve(self, ident: str) -> str:
        """Turn a short id (or a full job key) into the job key."""
        row = self.conn.execute("SELECT key FROM jobs WHERE key = ?", (ident,)).fetchone()
        if row:
            return row["key"]
        matches = self.conn.execute(
            "SELECT key FROM jobs WHERE short_id LIKE ?", (ident.lower() + "%",)
        ).fetchall()
        if len(ident) >= 4 and len(matches) == 1:
            return matches[0]["key"]
        if len(matches) > 1:
            raise StorageError(f"id {ident!r} is ambiguous; use more characters")
        raise StorageError(f"no job with id {ident!r}")

    def mark(self, ident: str, status: str, note: str = "") -> str:
        if status not in STATUSES:
            raise StorageError(f"unknown status {status!r}; use one of: {', '.join(STATUSES)}")
        key = self.resolve(ident)
        with self.conn:
            if self._current_status(key) != status:
                self._add_history(key, status, note)
        return key

    def _current_status(self, key: str) -> str:
        row = self.conn.execute(
            "SELECT status FROM status_history WHERE job_key=? ORDER BY id DESC LIMIT 1", (key,)
        ).fetchone()
        return row["status"] if row else "found"

    def history(self, job_key: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT status, noted_at, note FROM status_history WHERE job_key=? ORDER BY id",
            (job_key,),
        )
        return [dict(r) for r in rows]

    # -- reading ---------------------------------------------------------------------

    def rows(self, include_inactive: bool = False) -> list[JobRow]:
        sql = (
            "SELECT j.*, d.verdict, d.reasons, d.score, d.breakdown, d.explanation, d.rationale, "
            "d.role_match, "
            "(SELECT status FROM status_history h WHERE h.job_key = j.key "
            " ORDER BY h.id DESC LIMIT 1) AS status "
            "FROM jobs j LEFT JOIN decisions d ON d.job_key = j.key "
            + ("" if include_inactive else "WHERE j.active = 1 ")
            + "ORDER BY j.key"
        )
        result: list[JobRow] = []
        for r in self.conn.execute(sql):
            job = Job(
                company=r["company"], title=r["title"], location=r["location"],
                description=r["description"], url=r["url"],
                posted_at=datetime.fromisoformat(r["posted_at"]) if r["posted_at"] else None,
                ats=r["ats"], ats_job_id=r["ats_job_id"], workplace_type=r["workplace_type"],
            )  # fmt: skip
            result.append(
                JobRow(
                    job=job,
                    short_id=r["short_id"],
                    first_seen=r["first_seen"],
                    last_seen=r["last_seen"],
                    active=bool(r["active"]),
                    status=r["status"] or "found",
                    verdict=r["verdict"],
                    reasons=json.loads(r["reasons"]) if r["reasons"] else [],
                    score=r["score"],
                    parts=json.loads(r["breakdown"]) if r["breakdown"] else {},
                    explanation=r["explanation"],
                    rationale=r["rationale"],
                    role_match=r["role_match"],
                )
            )
        return result
