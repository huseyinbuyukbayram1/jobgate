from datetime import UTC, date, datetime

import pytest

from jobgate.filters import Reason, Verdict
from jobgate.models import Job
from jobgate.storage import STATUSES, Storage, StorageError


def make_job(n=1, company="Acme", title=None, ats="greenhouse"):
    return Job(
        company=company,
        title=title or f"Engineer {n}",
        location="Berlin, Germany",
        description="Build things.",
        url=f"https://example.com/{n}",
        posted_at=datetime(2026, 1, 1, tzinfo=UTC),
        ats=ats,
        ats_job_id=str(n),
    )


@pytest.fixture
def store(tmp_path):
    with Storage(tmp_path / "jobs.db") as s:
        yield s


def count(store, table):
    return store.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_upserting_the_same_jobs_twice_creates_no_duplicates(store):
    jobs = [make_job(1), make_job(2)]
    assert store.upsert_jobs(jobs, date(2026, 1, 1)) == 2
    assert store.upsert_jobs(jobs, date(2026, 1, 2)) == 0
    assert count(store, "jobs") == 2
    assert count(store, "status_history") == 2  # one "found" per job, not per run


def test_upsert_updates_changed_fields_but_keeps_first_seen(store):
    store.upsert_jobs([make_job(1, title="Old title")], date(2026, 1, 1))
    store.upsert_jobs([make_job(1, title="New title")], date(2026, 1, 5))
    row = store.rows()[0]
    assert row.job.title == "New title"
    assert row.first_seen == "2026-01-01"
    assert row.last_seen == "2026-01-05"


def test_new_jobs_start_with_status_found(store):
    store.upsert_jobs([make_job(1)], date(2026, 1, 1))
    assert store.rows()[0].status == "found"


def test_postings_that_disappear_from_a_fetched_company_become_inactive(store):
    a, b = make_job(1, company="Acme"), make_job(2, company="Beta", ats="lever")
    store.upsert_jobs([a, b], date(2026, 1, 1))
    # Acme was fetched fine and no longer lists job 1; Beta failed, so it is untouched
    closed = store.deactivate_missing({("greenhouse", "Acme")}, set(), date(2026, 1, 2))
    assert closed == 1
    assert [r.job.ats_job_id for r in store.rows()] == ["2"]
    assert len(store.rows(include_inactive=True)) == 2


def test_a_posting_that_comes_back_is_active_again(store):
    job = make_job(1)
    store.upsert_jobs([job], date(2026, 1, 1))
    store.deactivate_missing({("greenhouse", "Acme")}, set(), date(2026, 1, 2))
    store.upsert_jobs([job], date(2026, 1, 3))
    assert len(store.rows()) == 1


def test_decisions_are_replaced_not_duplicated(store):
    job = make_job(1)
    store.upsert_jobs([job], date(2026, 1, 1))
    reasons = [Reason("EXPERIENCE_TOO_HIGH", Verdict.REJECT, "5+ years of experience.")]
    for _ in range(2):
        store.save_decision(job.key, Verdict.REJECT, reasons)
    assert count(store, "decisions") == 1
    row = store.rows()[0]
    assert row.verdict == "reject"
    assert row.reasons[0]["code"] == "EXPERIENCE_TOO_HIGH"
    assert row.reasons[0]["evidence"] == "5+ years of experience."


def test_scores_are_stored_and_a_reject_clears_them(store):
    job = make_job(1)
    store.upsert_jobs([job], date(2026, 1, 1))
    store.save_decision(job.key, Verdict.PASS, [])
    store.save_score(job.key, 72, {"role": 28, "technology": 20}, "72: role 28, technology 20")
    row = store.rows()[0]
    assert (row.score, row.parts, row.explanation) == (
        72,
        {"role": 28, "technology": 20},
        "72: role 28, technology 20",
    )
    store.save_decision(job.key, Verdict.REJECT, [Reason("X", Verdict.REJECT, "e")])
    assert store.rows()[0].score is None


def test_mark_appends_history_and_changes_current_status(store):
    job = make_job(1)
    store.upsert_jobs([job], date(2026, 1, 1))
    short = store.rows()[0].short_id
    assert store.mark(short, "applied", note="sent CV") == job.key
    assert store.rows()[0].status == "applied"
    history = store.history(job.key)
    assert [h["status"] for h in history] == ["found", "applied"]
    assert history[-1]["note"] == "sent CV"


def test_marking_the_same_status_twice_adds_nothing(store):
    job = make_job(1)
    store.upsert_jobs([job], date(2026, 1, 1))
    short = store.rows()[0].short_id
    store.mark(short, "applied")
    store.mark(short, "applied")
    assert count(store, "status_history") == 2


def test_manual_status_survives_later_runs(store):
    job = make_job(1)
    store.upsert_jobs([job], date(2026, 1, 1))
    store.mark(store.rows()[0].short_id, "applied")
    store.upsert_jobs([job], date(2026, 1, 2))
    assert store.rows()[0].status == "applied"


def test_mark_accepts_the_full_key_and_rejects_bad_input(store):
    job = make_job(1)
    store.upsert_jobs([job], date(2026, 1, 1))
    assert store.mark(job.key, "dropped") == job.key
    with pytest.raises(StorageError, match="status"):
        store.mark(job.key, "maybe")
    with pytest.raises(StorageError, match="no job"):
        store.mark("deadbeef", "applied")
    assert set(STATUSES) == {"found", "applied", "dropped"}


def test_run_log_is_recorded(store):
    store.record_run(date(2026, 1, 1), jobs_seen=5, new_jobs=3, failures=["Beta: not_found"])
    row = store.conn.execute("SELECT jobs_seen, new_jobs, failures FROM runs").fetchone()
    assert (row[0], row[1]) == (5, 3)
    assert "Beta" in row[2]


def test_database_file_persists_between_connections(tmp_path):
    path = tmp_path / "jobs.db"
    with Storage(path) as s:
        s.upsert_jobs([make_job(1)], date(2026, 1, 1))
    with Storage(path) as s:
        assert len(s.rows()) == 1


def test_rationale_is_stored_separately_from_the_score_and_survives_an_identical_rescore(tmp_path):
    from datetime import date

    from jobgate.filters import Verdict

    job = Job(
        company="Acme", title="Engineer", location="Berlin", description="d",
        url="https://example.com/1", ats="greenhouse", ats_job_id="1",
    )  # fmt: skip
    with Storage(tmp_path / "s.db") as store:
        store.upsert_jobs([job], date(2026, 1, 1))
        store.save_decision(job.key, Verdict.PASS, [])
        store.save_score(job.key, 70, {"role": 30}, "70: role 30")
        store.save_rationale(job.key, "Good fit.")
        assert store.rows()[0].rationale == "Good fit."
        store.save_score(job.key, 70, {"role": 30}, "70: role 30")  # same score again
        assert store.rows()[0].rationale == "Good fit."
        store.save_score(job.key, 55, {"role": 25}, "55: role 25")  # score changed
        row = store.rows()[0]
        assert row.rationale is None and row.score == 55


def test_old_databases_get_the_rationale_column(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE decisions (job_key TEXT PRIMARY KEY, verdict TEXT NOT NULL, "
        "reasons TEXT NOT NULL, score INTEGER, breakdown TEXT, explanation TEXT);"
    )
    conn.close()
    Storage(path).close()
    cols = [r[1] for r in sqlite3.connect(path).execute("PRAGMA table_info(decisions)")]
    assert "rationale" in cols
