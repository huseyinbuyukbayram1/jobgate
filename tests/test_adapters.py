import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from jobgate.adapters import ADAPTERS
from jobgate.adapters.ashby import AshbyAdapter
from jobgate.adapters.greenhouse import GreenhouseAdapter
from jobgate.adapters.lever import LeverAdapter
from jobgate.http import FetchError, HttpClient

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def client_returning(tmp_path, payload, seen=None):
    def handler(request):
        if seen is not None:
            seen.append(request.url)
        return httpx.Response(200, json=payload)

    return HttpClient(cache_dir=tmp_path, min_interval=0, transport=httpx.MockTransport(handler))


def test_registry_contains_the_three_supported_sources():
    assert set(ADAPTERS) == {"greenhouse", "lever", "ashby"}


# -- Greenhouse -------------------------------------------------------------------------


def test_greenhouse_request_asks_for_content(tmp_path):
    seen = []
    client = client_returning(tmp_path, load("greenhouse_jobs.json"), seen)
    GreenhouseAdapter().fetch(client, "Acme", "acme")
    assert seen[0].host == "boards-api.greenhouse.io"
    assert seen[0].path == "/v1/boards/acme/jobs"
    assert seen[0].params["content"] == "true"


def test_greenhouse_normalizes_jobs_and_skips_malformed_ones():
    jobs = GreenhouseAdapter().parse(load("greenhouse_jobs.json"), "Acme")
    assert [j.ats_job_id for j in jobs] == ["1001", "1002"]  # empty title skipped
    first = jobs[0]
    assert first.company == "Acme"
    assert first.title == "Junior Software Engineer"
    assert first.location == "Berlin, Germany"
    assert first.url == "https://boards.example.com/acme/jobs/1001"
    assert first.ats == "greenhouse"
    assert first.description == "Build & ship APIs.\nPython\nSQL"
    assert first.posted_at == datetime(2026, 1, 2, 13, 30, tzinfo=UTC)


def test_greenhouse_falls_back_to_updated_at_when_no_first_published():
    second = GreenhouseAdapter().parse(load("greenhouse_jobs.json"), "Acme")[1]
    assert second.posted_at == datetime(2026, 2, 1, 15, 0, tzinfo=UTC)
    assert second.description == ""


def test_greenhouse_rejects_unexpected_shape():
    with pytest.raises(FetchError) as exc:
        GreenhouseAdapter().parse({"unexpected": []}, "Acme")
    assert exc.value.kind == "invalid_response"


# -- Lever ------------------------------------------------------------------------------


def test_lever_request_uses_json_mode(tmp_path):
    seen = []
    client = client_returning(tmp_path, load("lever_postings.json"), seen)
    LeverAdapter().fetch(client, "Acme", "acme")
    assert seen[0].host == "api.lever.co"
    assert seen[0].path == "/v0/postings/acme"
    assert seen[0].params["mode"] == "json"


def test_lever_eu_request_goes_to_the_eu_host_with_the_same_path_and_json_mode(tmp_path):
    seen = []
    client = client_returning(tmp_path, load("lever_postings.json"), seen)
    jobs = LeverAdapter().fetch(client, "Acme", "acme", region="eu")
    assert seen[0].scheme == "https" and seen[0].host == "api.eu.lever.co"
    assert seen[0].path == "/v0/postings/acme"
    assert seen[0].params["mode"] == "json"
    assert [j.ats for j in jobs] == ["lever"] * len(jobs) and jobs


def test_lever_defaults_to_the_global_host_and_rejects_an_unknown_region(tmp_path):
    seen = []
    client = client_returning(tmp_path, load("lever_postings.json"), seen)
    LeverAdapter().fetch(client, "Acme", "acme", region="global")
    assert seen[0].host == "api.lever.co"
    with pytest.raises(ValueError, match="region"):
        LeverAdapter().request("acme", region="mars")


def test_lever_normalizes_postings_and_skips_malformed_ones():
    jobs = LeverAdapter().parse(load("lever_postings.json"), "Acme")
    assert [j.ats_job_id for j in jobs] == [
        "aaaaaaaa-0000-0000-0000-000000000001",
        "aaaaaaaa-0000-0000-0000-000000000002",
    ]
    first = jobs[0]
    assert first.title == "Graduate Backend Engineer"
    assert first.location == "London, UK"
    assert first.url.endswith("000000000001")
    assert first.workplace_type == "hybrid"
    assert first.posted_at == datetime(2026, 1, 1, tzinfo=UTC)
    assert "Join the platform team." in first.description
    assert "Write services" in first.description
    assert "We value curiosity." in first.description


def test_lever_location_falls_back_to_all_locations():
    second = LeverAdapter().parse(load("lever_postings.json"), "Acme")[1]
    assert second.location == "Dublin, Ireland"
    assert second.posted_at is None


def test_lever_rejects_unexpected_shape():
    with pytest.raises(FetchError) as exc:
        LeverAdapter().parse({"ok": False}, "Acme")
    assert exc.value.kind == "invalid_response"


# -- Ashby ------------------------------------------------------------------------------


def test_ashby_request_includes_compensation(tmp_path):
    seen = []
    client = client_returning(tmp_path, load("ashby_board.json"), seen)
    AshbyAdapter().fetch(client, "Acme", "acme")
    assert seen[0].host == "api.ashbyhq.com"
    assert seen[0].path == "/posting-api/job-board/acme"
    assert seen[0].params["includeCompensation"] == "true"


def test_ashby_normalizes_jobs_and_skips_unlisted():
    jobs = AshbyAdapter().parse(load("ashby_board.json"), "Acme")
    assert len(jobs) == 2  # unlisted job dropped
    first = jobs[0]
    assert first.ats_job_id == "bbbbbbbb-0000-0000-0000-000000000001"
    assert first.title == "Associate Software Engineer"
    assert first.location == "Amsterdam, Netherlands"
    assert first.description == "Work on core product."
    assert first.workplace_type == "Hybrid"
    assert first.posted_at == datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


def test_ashby_derives_id_from_job_url_when_missing():
    second = AshbyAdapter().parse(load("ashby_board.json"), "Acme")[1]
    assert second.ats_job_id == "cccccccc-0000-0000-0000-000000000002"
    assert second.description == "Design things."
    assert second.url.endswith("000000000002")


def test_ashby_rejects_unexpected_shape():
    with pytest.raises(FetchError) as exc:
        AshbyAdapter().parse([], "Acme")
    assert exc.value.kind == "invalid_response"
