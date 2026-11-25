import csv
import io
from datetime import date
from pathlib import Path

import pytest

from jobgate.models import Job
from jobgate.profile import load_profile
from jobgate.report import build_csv, build_markdown
from jobgate.scoring import score_job
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


# -- low role match: postings whose role score is 0 stay out of "Ranked matches" ---------

PROFILE = load_profile(Path(__file__).parent.parent / "profile.example.yaml")


def scored_row(n, title, verdict="pass", description="Work with Python and SQL.", **kw):
    job = Job(
        company=kw.get("company", "Acme"),
        title=title,
        location="Berlin, Germany",
        description=description,
        url=f"https://example.com/{n}",
        ats="greenhouse",
        ats_job_id=str(n),
    )
    result = score_job(job, PROFILE)
    return JobRow(
        job=job,
        short_id=f"{n:08x}",
        first_seen="2026-01-01",
        last_seen="2026-01-10",
        active=True,
        status="found",
        verdict=verdict,
        score=result.total,
        parts=result.parts,
        explanation=result.explain(),
    )


def section(text, name):
    """The text of one '## name' section."""
    after = text.split(f"## {name}", 1)[1]
    return after.split("\n## ", 1)[0]


def mixed_rows():
    return [
        scored_row(1, "Business Development Representative, DACH"),
        scored_row(2, "Software Engineering Intern"),
        scored_row(3, "Backend Engineer"),
        scored_row(4, "Account Executive, Mid-Market"),
    ]


def test_a_title_with_no_role_match_is_not_ranked_but_listed_as_low_role_match():
    rows = mixed_rows()
    assert rows[0].parts["role"] == 0 and rows[0].score > 0  # still scored and stored
    text = build_markdown(rows, DAY)
    ranked = section(text, "Ranked matches")
    low = section(text, "Low role match")
    assert "Business Development Representative" not in ranked
    assert "Business Development Representative" in low
    assert "Account Executive" in low and "Account Executive" not in ranked


def test_engineering_titles_stay_ranked():
    text = build_markdown(mixed_rows(), DAY)
    ranked = section(text, "Ranked matches")
    low = section(text, "Low role match")
    for title in ("Software Engineering Intern", "Backend Engineer"):
        assert title in ranked and title not in low


def test_low_role_entries_show_their_score_and_breakdown_with_role_zero():
    low = section(build_markdown(mixed_rows(), DAY), "Low role match")
    entry = next(line for line in low.splitlines() if "Business Development" in line)
    total = mixed_rows()[0].score
    assert f". {total}: role 0, technology" in entry and entry.startswith("### ")
    assert "`00000001`" in low


def test_low_role_matches_are_ordered_by_score_and_trimmed_like_the_other_lists():
    rows = [
        scored_row(1, "Sales Development Representative", description="x"),
        scored_row(2, "Business Analyst", description="Python, SQL and Docker."),
    ]
    low = section(build_markdown(rows, DAY), "Low role match")
    assert low.index("Business Analyst") < low.index("Sales Development")
    limited = section(build_markdown(rows, DAY, limit=1), "Low role match")
    assert "Business Analyst" in limited and "Sales Development" not in limited


def test_summary_line_counts_low_role_matches_separately():
    text = build_markdown(mixed_rows(), DAY)
    assert "2 matches, 2 low role match, 0 to check" in text
    assert "No matches" in build_markdown([scored_row(1, "Sales Rep")], DAY)


REASONS = [{"code": "LOCATION_UNCLEAR", "verdict": "check", "evidence": "Hybrid"}]


def check_row(n, title):
    row = scored_row(n, title, verdict="check")
    row.reasons = REASONS
    return row


def test_check_postings_with_a_zero_role_score_move_to_low_role_match_keeping_their_reasons():
    rows = [check_row(1, "Business Development Representative"), check_row(2, "Backend Engineer")]
    text = build_markdown(rows, DAY)
    needs_check = section(text, "Needs a check")
    low = section(text, "Low role match")
    assert "Backend Engineer" in needs_check and "Backend Engineer" not in low
    assert "Business Development" in low and "Business Development" not in needs_check
    assert "- LOCATION_UNCLEAR: Hybrid" in low  # the filter's reason is still shown
    assert "role 0" in low


def test_summary_counts_low_role_checks_in_low_role_and_not_in_to_check():
    rows = [*mixed_rows(), check_row(5, "Sales Rep"), check_row(6, "Data Engineer")]
    text = build_markdown(rows, DAY)
    assert "2 matches, 3 low role match, 1 to check" in text


def test_low_role_section_orders_passes_and_checks_together_by_score():
    rows = [check_row(1, "Business Analyst"), scored_row(2, "Sales Rep", description="x")]
    rows[0].score = 90  # only the order matters here
    low = section(build_markdown(rows, DAY), "Low role match")
    assert low.index("Business Analyst") < low.index("Sales Rep")


def test_csv_puts_low_role_checks_in_the_low_role_section_with_their_verdict():
    rows = [check_row(1, "Business Development Representative"), check_row(2, "Backend Engineer")]
    by_title = {r["title"]: r for r in csv.DictReader(io.StringIO(build_csv(rows)))}
    low = by_title["Business Development Representative"]
    assert low["section"] == "low_role_match" and low["verdict"] == "check" and low["rank"] == ""
    assert by_title["Backend Engineer"]["section"] == "check"
    assert by_title["Backend Engineer"]["rank"] == "1"


def test_rows_without_a_stored_breakdown_are_never_called_low_role():
    row = make_row(1, score=50)
    row.parts = {}
    text = build_markdown([row], DAY)
    assert "Engineer 1" in section(text, "Ranked matches")


def test_csv_marks_low_role_matches_and_leaves_their_rank_empty():
    parsed = list(csv.DictReader(io.StringIO(build_csv(mixed_rows()))))
    by_title = {r["title"]: r for r in parsed}
    low = by_title["Business Development Representative, DACH"]
    assert low["section"] == "low_role_match" and low["rank"] == "" and low["role_points"] == "0"
    assert int(low["score"]) > 0
    top = by_title["Backend Engineer"]
    assert top["section"] == "ranked" and top["role_points"] != "0"
    assert [r["rank"] for r in parsed if r["section"] == "ranked"] == ["1", "2"]
    assert [r["section"] for r in parsed][-2:] == ["low_role_match", "low_role_match"]


@pytest.mark.parametrize("builder", [build_markdown, build_csv])
def test_reports_with_low_role_matches_are_byte_identical_whatever_the_input_order(builder):
    rows = mixed_rows()
    args = (DAY,) if builder is build_markdown else ()
    first = builder(rows, *args)
    assert builder(list(reversed(rows)), *args) == first
    assert builder(rows, *args) == first


def test_the_role_match_is_shown_in_the_entry_and_the_csv():
    row = scored_row(1, "Member of Technical Staff - Workers AI")
    row.role_match = 'phrase "software engineer" via "member of technical staff"'
    text = build_markdown([row], DAY)
    assert 'role match: phrase "software engineer" via "member of technical staff"' in text
    record = list(csv.DictReader(io.StringIO(build_csv([row]))))[0]
    assert record["role_match"] == row.role_match


def test_entries_without_a_role_match_have_no_role_match_text():
    row = scored_row(1, "Backend Engineer")
    row.role_match = None
    assert "role match:" not in build_markdown([row], DAY)
    assert list(csv.DictReader(io.StringIO(build_csv([row]))))[0]["role_match"] == ""
