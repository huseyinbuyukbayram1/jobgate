import json
import shutil
import sqlite3
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from jobgate import cli
from jobgate.http import HttpClient

REPO_ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()

COMPANIES = """
companies:
  - {name: Alpha, ats: greenhouse, token: good}
  - {name: Beta, ats: lever, token: good}
  - {name: Gamma, ats: ashby, token: good}
  - {name: Gone, ats: greenhouse, token: gone}
"""


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def router(request):
    host, path = request.url.host, request.url.path
    if "/gone" in path:
        return httpx.Response(404, json={})
    if host == "boards-api.greenhouse.io":
        return httpx.Response(200, json=fixture("greenhouse_jobs.json"))
    if host == "api.lever.co":
        return httpx.Response(200, json=fixture("lever_postings.json"))
    if host == "api.ashbyhq.com":
        return httpx.Response(200, json=fixture("ashby_board.json"))
    return httpx.Response(500)


@pytest.fixture
def env(tmp_path, monkeypatch):
    shutil.copy(REPO_ROOT / "profile.example.yaml", tmp_path / "profile.yaml")
    (tmp_path / "companies.yaml").write_text(COMPANIES, encoding="utf-8")
    monkeypatch.setattr(
        cli,
        "make_client",
        lambda opts: HttpClient(
            cache_dir=tmp_path / "cache",
            min_interval=0,
            max_retries=0,
            transport=httpx.MockTransport(router),
        ),
    )
    base = [
        "--db", str(tmp_path / "jobs.db"),
        "--profile", str(tmp_path / "profile.yaml"),
        "--companies", str(tmp_path / "companies.yaml"),
        "--reports-dir", str(tmp_path / "reports"),
    ]  # fmt: skip
    return tmp_path, base


def invoke(base, *args):
    return runner.invoke(cli.app, [*base, *args])


def table_counts(path):
    conn = sqlite3.connect(path)
    return {
        t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in ("jobs", "decisions", "status_history")
    }


def test_run_creates_a_ranked_report_from_fetched_jobs(env):
    tmp, base = env
    result = invoke(base, "run")
    assert result.exit_code == 0, result.output
    report = (tmp / "reports" / "report.md").read_text(encoding="utf-8")
    assert "## Ranked matches" in report
    assert "Junior Software Engineer" in report
    assert "(https://boards.example.com/acme/jobs/1001)" in report
    assert (tmp / "reports" / "report.csv").exists()


def test_running_twice_creates_no_duplicate_records(env):
    tmp, base = env
    assert invoke(base, "run").exit_code == 0
    first = table_counts(tmp / "jobs.db")
    first_report = (tmp / "reports" / "report.md").read_text(encoding="utf-8")
    first_csv = (tmp / "reports" / "report.csv").read_text(encoding="utf-8")
    assert invoke(base, "run").exit_code == 0
    assert table_counts(tmp / "jobs.db") == first
    assert (tmp / "reports" / "report.md").read_text(encoding="utf-8") == first_report
    assert (tmp / "reports" / "report.csv").read_text(encoding="utf-8") == first_csv


@pytest.mark.parametrize("command", ["fetch", "filter", "score", "report"])
def test_each_command_is_idempotent_on_its_own(env, command):
    tmp, base = env
    for prep in ("fetch", "filter", "score"):
        assert invoke(base, prep).exit_code == 0
    assert invoke(base, command).exit_code == 0
    before = table_counts(tmp / "jobs.db")
    assert invoke(base, command).exit_code == 0
    assert table_counts(tmp / "jobs.db") == before


def test_a_failing_company_is_reported_but_does_not_stop_the_run(env):
    tmp, base = env
    result = invoke(base, "fetch")
    assert result.exit_code == 0
    assert "Gone" in result.output and "not_found" in result.output
    assert table_counts(tmp / "jobs.db")["jobs"] > 0


def test_fetch_exits_with_error_when_every_company_fails(env):
    tmp, base = env
    (tmp / "companies.yaml").write_text(
        "companies:\n  - {name: Gone, ats: greenhouse, token: gone}\n", encoding="utf-8"
    )
    result = invoke(base, "fetch")
    assert result.exit_code == 1
    assert "every company failed" in result.output.lower()


def test_filter_sorts_postings_into_pass_check_and_reject(env):
    _, base = env
    invoke(base, "fetch")
    result = invoke(base, "filter")
    assert result.exit_code == 0
    assert "pass" in result.output and "check" in result.output and "reject" in result.output


def test_score_before_filter_explains_what_to_do(env):
    _, base = env
    invoke(base, "fetch")
    result = invoke(base, "score")
    assert result.exit_code == 1
    assert "jobgate filter" in result.output


def test_mark_changes_the_status_and_the_report_shows_it(env):
    tmp, base = env
    invoke(base, "run")
    conn = sqlite3.connect(tmp / "jobs.db")
    short = conn.execute(
        "SELECT short_id FROM jobs WHERE title = 'Junior Software Engineer'"
    ).fetchone()[0]
    result = invoke(base, "mark", short, "applied", "--note", "sent")
    assert result.exit_code == 0, result.output
    invoke(base, "report")
    assert "status: applied" in (tmp / "reports" / "report.md").read_text(encoding="utf-8")


def test_mark_rejects_unknown_status_and_unknown_id(env):
    _, base = env
    invoke(base, "run")
    bad_status = invoke(base, "mark", "abcd1234", "maybe")
    assert bad_status.exit_code != 0
    bad_id = invoke(base, "mark", "abcd1234", "applied")
    assert bad_id.exit_code == 2
    assert "no job with id" in bad_id.output


def test_missing_profile_gives_a_clear_error(env):
    tmp, base = env
    (tmp / "profile.yaml").unlink()
    result = invoke(base, "filter")
    assert result.exit_code == 2
    assert "profile file not found" in result.output


def test_companies_validate_reports_counts_and_errors(env):
    tmp, base = env
    ok = invoke(base, "companies", "validate")
    assert ok.exit_code == 0
    assert "4 companies" in ok.output
    (tmp / "companies.yaml").write_text("companies:\n  - {name: A, ats: workday, token: a}\n")
    bad = invoke(base, "companies", "validate")
    assert bad.exit_code == 1
    assert "workday" in bad.output


def test_help_texts_are_in_english_and_list_every_command():
    result = runner.invoke(cli.app, ["--help"])
    assert result.exit_code == 0
    for word in ("fetch", "filter", "score", "report", "mark", "run", "companies"):
        assert word in result.output
    assert "never applies" in result.output.lower()
