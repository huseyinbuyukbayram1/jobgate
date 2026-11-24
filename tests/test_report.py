import csv
import io
from datetime import date

from jobgate.models import Job
from jobgate.report import build_csv, build_markdown
from jobgate.storage import JobRow

DAY = date(2026, 1, 10)


def make_row(n, verdict="pass", score=50, status="found", title=None, reasons=None, **kw):
    job = Job(
        company=kw.get("company", "Acme"),
        title=title or f"Engineer {n}",
        location="Berlin, Germany",
        description="x",
        url=f"https://example.com/{n}",
        ats="greenhouse",
        ats_job_id=str(n),
    )
    return JobRow(
        job=job,
        short_id=f"{n:08x}",
        first_seen="2026-01-01",
        last_seen="2026-01-10",
        active=True,
        status=status,
        verdict=verdict,
        reasons=reasons or [],
        score=score if verdict != "reject" else None,
        parts={"role": 28, "technology": 20} if verdict != "reject" else {},
        explanation=f"{score}: role 28, technology 20" if verdict != "reject" else None,
    )


def test_matches_are_ranked_by_score_descending():
    rows = [make_row(1, score=40), make_row(2, score=90), make_row(3, score=65)]
    text = build_markdown(rows, DAY)
    assert text.index("Engineer 2") < text.index("Engineer 3") < text.index("Engineer 1")


def test_ties_are_broken_by_company_then_title_so_output_is_stable():
    rows = [make_row(1, score=50, company="Zed"), make_row(2, score=50, company="Acme")]
    assert build_markdown(rows, DAY) == build_markdown(list(reversed(rows)), DAY)
    assert build_markdown(rows, DAY).index("Acme") < build_markdown(rows, DAY).index("Zed")


def test_each_entry_shows_the_score_breakdown_link_and_id():
    text = build_markdown([make_row(1, score=72)], DAY)
    assert "72: role 28, technology 20" in text
    assert "https://example.com/1" in text
    assert "`00000001`" in text


def test_check_postings_are_in_their_own_section_with_reasons():
    reasons = [{"code": "LOCATION_UNCLEAR", "verdict": "check", "evidence": "Remote"}]
    rows = [
        make_row(1, verdict="pass", score=80),
        make_row(2, verdict="check", score=60, reasons=reasons),
    ]
    text = build_markdown(rows, DAY)
    matches, check = text.split("## Needs a check")
    assert "Engineer 1" in matches and "Engineer 2" not in matches
    assert "Engineer 2" in check
    assert "LOCATION_UNCLEAR" in check and "Remote" in check


def test_rejected_postings_are_only_counted_by_reason():
    reasons = [{"code": "EXPERIENCE_TOO_HIGH", "verdict": "reject", "evidence": "5+ years"}]
    rows = [
        make_row(1),
        make_row(2, verdict="reject", reasons=reasons),
        make_row(3, verdict="reject", reasons=reasons),
    ]
    text = build_markdown(rows, DAY)
    assert "Engineer 2" not in text
    assert "EXPERIENCE_TOO_HIGH: 2" in text


def test_dropped_postings_are_hidden_and_applied_ones_are_marked():
    rows = [make_row(1, status="dropped"), make_row(2, status="applied")]
    text = build_markdown(rows, DAY)
    assert "Engineer 1" not in text
    assert "applied" in text


def test_min_score_and_limit_trim_the_lists():
    rows = [make_row(i, score=100 - i * 10) for i in range(1, 6)]
    text = build_markdown(rows, DAY, min_score=75, limit=1)
    assert "Engineer 1" in text and "Engineer 2" not in text
    assert "Engineer 5" not in text


def test_summary_counts_and_empty_report_are_readable():
    text = build_markdown([], DAY)
    assert "# jobgate report" in text
    assert "No matches" in text
    summary = build_markdown([make_row(1), make_row(2, verdict="check")], DAY)
    assert "1 match" in summary and "1 to check" in summary


def test_titles_with_markup_characters_do_not_break_the_report():
    text = build_markdown([make_row(1, title="Engineer [x] | <b>\nline")], DAY)
    assert "\n" not in text.split("Engineer")[1].split("](")[0]


def test_csv_has_one_row_per_match_in_rank_order_with_a_header():
    rows = [make_row(1, score=40), make_row(2, score=90), make_row(3, verdict="reject")]
    parsed = list(csv.DictReader(io.StringIO(build_csv(rows))))
    assert [r["title"] for r in parsed] == ["Engineer 2", "Engineer 1"]
    assert parsed[0]["rank"] == "1" and parsed[0]["score"] == "90"
    assert parsed[0]["id"] == "00000002"
    assert set(parsed[0]) >= {"rank", "score", "verdict", "company", "title", "url", "status"}


def test_csv_can_include_rejected_postings_with_reason_codes():
    reasons = [{"code": "EXPERIENCE_TOO_HIGH", "verdict": "reject", "evidence": "5+ years"}]
    rows = [make_row(1), make_row(2, verdict="reject", reasons=reasons)]
    parsed = list(csv.DictReader(io.StringIO(build_csv(rows, include_rejected=True))))
    assert len(parsed) == 2
    assert parsed[1]["verdict"] == "reject" and parsed[1]["reasons"] == "EXPERIENCE_TOO_HIGH"


def test_rationale_is_shown_under_the_entry_and_in_the_csv_when_present():
    row = make_row(1, score=72)
    row.rationale = "Title matches your target role."
    text = build_markdown([row], DAY)
    assert "> Title matches your target role." in text
    records = list(csv.DictReader(io.StringIO(build_csv([row]))))
    assert records[0]["rationale"] == "Title matches your target role."


def test_reports_without_rationale_have_no_quote_lines_and_an_empty_csv_cell():
    row = make_row(1, score=72)
    assert "\n> " not in build_markdown([row], DAY)
    assert list(csv.DictReader(io.StringIO(build_csv([row]))))[0]["rationale"] == ""
