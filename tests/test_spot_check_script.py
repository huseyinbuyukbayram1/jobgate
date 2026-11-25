"""scripts/spot_check_sample.py draws the spot-check rows in docs/spot_checks.md."""

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest

from jobgate.filters import Reason, Verdict
from jobgate.models import Job
from jobgate.storage import Storage

SCRIPT = Path(__file__).parent.parent / "scripts" / "spot_check_sample.py"
STUDENT = "STUDENT_STATUS_REQUIRED"
YEAR = "GRADUATION_YEAR_MISMATCH"


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("spot_check_sample", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look the module up by name
    spec.loader.exec_module(module)
    return module


def add(store, n, codes, company="Acme"):
    job = Job(
        company=company,
        title=f"Intern {n}",
        location="Berlin",
        description="d",
        url=f"https://example.com/{n}",
        ats="greenhouse",
        ats_job_id=str(n),
    )
    store.upsert_jobs([job], date(2026, 1, 1))
    reasons = [Reason(code, Verdict.REJECT, f"evidence {n} for {code}") for code in codes]
    store.save_decision(job.key, Verdict.REJECT if reasons else Verdict.PASS, reasons)


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "jobs.db"
    with Storage(path) as store:
        for n in range(1, 31):  # 30 postings where the student code is the first reason
            add(store, n, [STUDENT])
        for n in range(31, 36):  # 5 where another code comes first
            add(store, n, ["LOCATION_OUTSIDE_PROFILE", STUDENT])
        for n in range(36, 40):  # 4 year-mismatch postings, all primary
            add(store, n, [YEAR])
        add(store, 40, ["LOCATION_OUTSIDE_PROFILE", YEAR])  # 1 non-primary
        add(store, 41, [])  # passes the filter, never sampled
    return path


def test_the_same_seed_draws_the_same_rows_and_another_seed_draws_others(script, db):
    first = script.draw(db, [STUDENT], count=10, seed=42)
    again = script.draw(db, [STUDENT], count=10, seed=42)
    other = script.draw(db, [STUDENT], count=10, seed=7)
    assert first == again
    assert [r.title for r in first[STUDENT]] != [r.title for r in other[STUDENT]]


def test_primary_rows_are_preferred_and_flagged_as_such(script, db):
    rows = script.draw(db, [STUDENT], count=10, seed=42)[STUDENT]
    assert len(rows) == 10 and all(r.primary for r in rows)
    assert len({r.title for r in rows}) == 10


def test_fewer_primary_rows_than_asked_are_filled_with_flagged_others(script, db):
    rows = script.draw(db, [YEAR], count=10, seed=42)[YEAR]
    assert len(rows) == 5  # only 5 postings carry the code at all
    assert [r.primary for r in rows].count(True) == 4
    other = next(r for r in rows if not r.primary)
    assert other.codes[0] == "LOCATION_OUTSIDE_PROFILE"


def test_the_markdown_has_company_title_code_evidence_as_stored_and_link(script, db):
    rows = script.draw(db, [YEAR], count=2, seed=42)
    text = script.to_markdown(rows, seed=42)
    assert "seed 42" in text and f"## {YEAR}" in text
    first = rows[YEAR][0]
    assert first.company in text and first.title in text and first.url in text
    assert first.evidence in text  # the evidence sentence, untouched


def test_the_command_line_writes_a_file_and_rejects_unknown_input(script, db, tmp_path, capsys):
    out = tmp_path / "sample.md"
    assert script.main(["--db", str(db), "--codes", STUDENT, "--out", str(out), "--seed", "1"]) == 0
    assert STUDENT in out.read_text(encoding="utf-8")
    assert script.main(["--db", str(tmp_path / "missing.db")]) == 2
    assert "error:" in capsys.readouterr().err
    assert script.main(["--db", str(db), "--count", "0"]) == 2
