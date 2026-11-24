from datetime import date

import httpx
import pytest

from jobgate.http import FetchError, HttpClient

UA = "jobgate-test/0.0 (+https://github.com/example/jobgate)"


class FakeTime:
    """Deterministic clock whose sleep() advances time instead of waiting."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def make_client(tmp_path, handler, *, ft=None, today=date(2026, 1, 1), **kwargs):
    ft = ft or FakeTime()
    kwargs.setdefault("min_interval", 0.0)
    client = HttpClient(
        cache_dir=tmp_path,
        user_agent=UA,
        transport=httpx.MockTransport(handler),
        sleep=ft.sleep,
        clock=ft.clock,
        today=lambda: today,
        **kwargs,
    )
    return client, ft


def test_get_json_sends_explicit_user_agent(tmp_path):
    seen = []

    def handler(request):
        seen.append(request.headers["user-agent"])
        return httpx.Response(200, json={"ok": True})

    client, _ = make_client(tmp_path, handler)
    assert client.get_json("https://example.com/a") == {"ok": True}
    assert seen == [UA]


def test_same_url_same_day_hits_network_once(tmp_path):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json=[1, 2])

    client, _ = make_client(tmp_path, handler)
    assert client.get_json("https://example.com/a") == [1, 2]
    assert client.get_json("https://example.com/a") == [1, 2]
    assert len(calls) == 1


def test_cache_survives_new_client_instance(tmp_path):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json={"n": 1})

    make_client(tmp_path, handler)[0].get_json("https://example.com/a")
    make_client(tmp_path, handler)[0].get_json("https://example.com/a")
    assert len(calls) == 1


def test_cache_is_not_reused_on_another_day(tmp_path):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json={"n": 1})

    make_client(tmp_path, handler, today=date(2026, 1, 1))[0].get_json("https://example.com/a")
    make_client(tmp_path, handler, today=date(2026, 1, 2))[0].get_json("https://example.com/a")
    assert len(calls) == 2


def test_different_params_are_cached_separately(tmp_path):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json={})

    client, _ = make_client(tmp_path, handler)
    client.get_json("https://example.com/a", params={"content": "true"})
    client.get_json("https://example.com/a")
    assert len(calls) == 2


def test_no_cache_flag_always_fetches(tmp_path):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json={})

    client, _ = make_client(tmp_path, handler, use_cache=False)
    client.get_json("https://example.com/a")
    client.get_json("https://example.com/a")
    assert len(calls) == 2


def test_retries_server_errors_with_increasing_backoff(tmp_path):
    responses = iter([500, 502, 200])

    def handler(request):
        status = next(responses)
        return httpx.Response(status, json={"ok": True})

    client, ft = make_client(tmp_path, handler, backoff_base=1.0)
    assert client.get_json("https://example.com/a") == {"ok": True}
    assert ft.sleeps == [1.0, 2.0]


def test_gives_up_after_three_retries(tmp_path):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503)

    client, ft = make_client(tmp_path, handler, backoff_base=1.0)
    with pytest.raises(FetchError) as exc:
        client.get_json("https://example.com/a")
    assert exc.value.kind == "http_error"
    assert exc.value.status == 503
    assert len(calls) == 4  # first try + 3 retries
    assert ft.sleeps == [1.0, 2.0, 4.0]


def test_retries_rate_limit_responses(tmp_path):
    responses = iter([429, 200])
    client, _ = make_client(tmp_path, lambda r: httpx.Response(next(responses), json={}))
    assert client.get_json("https://example.com/a") == {}


def test_retries_timeouts_then_reports_them(tmp_path):
    calls = []

    def handler(request):
        calls.append(1)
        raise httpx.ConnectTimeout("slow", request=request)

    client, _ = make_client(tmp_path, handler)
    with pytest.raises(FetchError) as exc:
        client.get_json("https://example.com/a")
    assert exc.value.kind == "network_error"
    assert len(calls) == 4


def test_not_found_is_not_retried(tmp_path):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(404, json={"error": "nope"})

    client, ft = make_client(tmp_path, handler)
    with pytest.raises(FetchError) as exc:
        client.get_json("https://example.com/a")
    assert exc.value.kind == "not_found"
    assert len(calls) == 1
    assert ft.sleeps == []


def test_invalid_json_is_reported_and_not_cached(tmp_path):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, text="<html>not json</html>")

    client, _ = make_client(tmp_path, handler)
    for _ in range(2):
        with pytest.raises(FetchError) as exc:
            client.get_json("https://example.com/a")
        assert exc.value.kind == "invalid_response"
    assert len(calls) == 2


def test_failed_requests_are_not_cached(tmp_path):
    responses = iter([404, 200])
    client, _ = make_client(tmp_path, lambda r: httpx.Response(next(responses), json={"a": 1}))
    with pytest.raises(FetchError):
        client.get_json("https://example.com/a")
    assert client.get_json("https://example.com/a") == {"a": 1}


def test_waits_between_network_requests_but_not_for_cache_hits(tmp_path):
    client, ft = make_client(tmp_path, lambda r: httpx.Response(200, json={}), min_interval=2.0)
    client.get_json("https://example.com/a")
    client.get_json("https://example.com/b")
    client.get_json("https://example.com/a")  # cache hit, no wait
    assert ft.sleeps == [2.0]
