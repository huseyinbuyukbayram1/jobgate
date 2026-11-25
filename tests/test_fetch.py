import json
from pathlib import Path

import httpx

from jobgate.companies import Company, CompanyConfig
from jobgate.fetch import fetch_all
from jobgate.http import HttpClient

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_client(tmp_path, handler):
    return HttpClient(
        cache_dir=tmp_path,
        min_interval=0,
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )


def router(request):
    host, path = request.url.host, request.url.path
    if host == "boards-api.greenhouse.io" and "/good" in path:
        return httpx.Response(200, json=fixture("greenhouse_jobs.json"))
    if host == "api.lever.co" and "/good" in path:
        return httpx.Response(200, json=fixture("lever_postings.json"))
    if host == "api.eu.lever.co" and "/eu-good" in path:
        return httpx.Response(200, json=fixture("lever_postings.json"))
    if host == "api.ashbyhq.com" and "/good" in path:
        return httpx.Response(200, json=fixture("ashby_board.json"))
    if "/gone" in path:
        return httpx.Response(404, json={})
    if "/boom" in path:
        raise RuntimeError("adapter exploded")
    return httpx.Response(500)


def config(*companies, sources=None):
    return CompanyConfig(
        sources=sources or {"greenhouse": True, "lever": True, "ashby": True},
        companies=list(companies),
    )


def test_collects_jobs_from_all_three_sources(tmp_path):
    cfg = config(
        Company(name="G", ats="greenhouse", token="good"),
        Company(name="L", ats="lever", token="good"),
        Company(name="A", ats="ashby", token="good"),
    )
    report = fetch_all(cfg, make_client(tmp_path, router))
    assert {j.ats for j in report.jobs} == {"greenhouse", "lever", "ashby"}
    assert len(report.jobs) == 2 + 2 + 2
    assert report.failures == []
    assert report.companies_ok == 3


def test_one_company_failing_does_not_stop_the_others(tmp_path):
    cfg = config(
        Company(name="Gone", ats="greenhouse", token="gone"),
        Company(name="Good", ats="lever", token="good"),
        Company(name="Down", ats="ashby", token="down"),
        Company(name="Also good", ats="ashby", token="good"),
    )
    report = fetch_all(cfg, make_client(tmp_path, router))
    assert report.companies_ok == 2
    assert len(report.jobs) == 4
    failed = {f.company: f.kind for f in report.failures}
    assert failed == {"Gone": "not_found", "Down": "http_error"}


def test_unexpected_exception_is_recorded_not_raised(tmp_path):
    cfg = config(
        Company(name="Boom", ats="greenhouse", token="boom"),
        Company(name="Good", ats="greenhouse", token="good"),
    )
    report = fetch_all(cfg, make_client(tmp_path, router))
    assert [f.company for f in report.failures] == ["Boom"]
    assert report.failures[0].kind == "unexpected"
    assert report.companies_ok == 1


def test_disabled_sources_and_companies_are_not_requested(tmp_path):
    seen = []

    def handler(request):
        seen.append(request.url.host)
        return router(request)

    cfg = config(
        Company(name="G", ats="greenhouse", token="good"),
        Company(name="L", ats="lever", token="good"),
        Company(name="Off", ats="ashby", token="good", enabled=False),
        sources={"greenhouse": True, "lever": False, "ashby": True},
    )
    report = fetch_all(cfg, make_client(tmp_path, handler))
    assert seen == ["boards-api.greenhouse.io"]
    assert report.companies_ok == 1


def test_duplicate_postings_are_dropped(tmp_path):
    # Config validation forbids this in files; fetch_all must still not duplicate.
    cfg = CompanyConfig.model_construct(
        sources={"greenhouse": True},
        companies=[
            Company(name="G", ats="greenhouse", token="good"),
            Company(name="G", ats="greenhouse", token="good"),
        ],
    )
    report = fetch_all(cfg, make_client(tmp_path, router))
    assert len(report.jobs) == 2


def test_report_lists_which_companies_succeeded(tmp_path):
    cfg = config(
        Company(name="Good", ats="lever", token="good"),
        Company(name="Gone", ats="greenhouse", token="gone"),
    )
    report = fetch_all(cfg, make_client(tmp_path, router))
    assert report.succeeded == [("lever", "Good")]


def test_a_lever_company_with_region_eu_is_fetched_from_the_eu_host(tmp_path):
    seen = []

    def handler(request):
        seen.append(request.url.host)
        return router(request)

    cfg = config(
        Company(name="Global", ats="lever", token="good"),
        Company(name="Europe", ats="lever", token="eu-good", region="eu"),
    )
    report = fetch_all(cfg, make_client(tmp_path, handler))
    assert report.failures == [] and report.companies_ok == 2
    assert sorted(seen) == ["api.eu.lever.co", "api.lever.co"]
    assert {j.company for j in report.jobs} == {"Global", "Europe"}


def test_an_eu_board_that_is_missing_is_a_failure_and_the_run_continues(tmp_path):
    cfg = config(
        Company(name="Gone", ats="lever", token="gone", region="eu"),
        Company(name="G", ats="greenhouse", token="good"),
    )
    report = fetch_all(cfg, make_client(tmp_path, router))
    assert [f.company for f in report.failures] == ["Gone"] and report.companies_ok == 1
