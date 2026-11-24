"""Polite HTTP client: explicit User-Agent, throttling, retries and a daily file cache."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from collections.abc import Callable, Mapping
from datetime import date
from pathlib import Path
from typing import Any, Literal

import httpx

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = "jobgate/0.1 (+https://github.com/huseyinbuyukbayram1/jobgate)"

ErrorKind = Literal["not_found", "http_error", "network_error", "invalid_response"]


class FetchError(Exception):
    """A request failed for good (after retries, where retrying makes sense)."""

    def __init__(self, kind: ErrorKind, url: str, message: str, status: int | None = None):
        super().__init__(f"{kind}: {message} ({url})")
        self.kind = kind
        self.url = url
        self.status = status


class HttpClient:
    """GET-JSON client used by every adapter.

    - Sends an explicit User-Agent that points at the project.
    - Waits ``min_interval`` seconds between real network requests.
    - Retries timeouts, network errors, HTTP 429 and 5xx up to ``max_retries`` times,
      with exponentially growing waits (``backoff_base`` * 2**attempt).
    - Caches successful responses on disk per calendar day, so the same endpoint is
      never requested twice on the same day.
    """

    def __init__(
        self,
        *,
        cache_dir: Path | str = ".jobgate_cache",
        user_agent: str = DEFAULT_USER_AGENT,
        min_interval: float = 1.0,
        timeout: float = 20.0,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        use_cache: bool = True,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._cache_dir = Path(cache_dir)
        self._min_interval = min_interval
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._use_cache = use_cache
        self._sleep = sleep
        self._clock = clock
        self._today = today
        self._last_request_at: float | None = None
        self._client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept": "application/json"},
            timeout=timeout,
            transport=transport,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def get_json(self, url: str, params: Mapping[str, str] | None = None) -> Any:
        full_url = str(httpx.URL(url, params=params))
        cached = self._read_cache(full_url)
        if cached is not None:
            logger.debug("cache hit: %s", full_url)
            return cached
        data = self._fetch(full_url)
        self._write_cache(full_url, data)
        return data

    # -- network ---------------------------------------------------------------------

    def _fetch(self, url: str) -> Any:
        attempt = 0
        while True:
            self._throttle()
            retry_reason: str
            try:
                response = self._client.get(url)
            except httpx.TransportError as exc:
                retry_reason = f"{type(exc).__name__}: {exc}"
                last_error = FetchError("network_error", url, retry_reason)
            else:
                self._last_request_at = self._clock()
                status = response.status_code
                if status == 404:
                    raise FetchError("not_found", url, "HTTP 404", status)
                if status == 429 or status >= 500:
                    retry_reason = f"HTTP {status}"
                    last_error = FetchError("http_error", url, retry_reason, status)
                elif status >= 400:
                    raise FetchError("http_error", url, f"HTTP {status}", status)
                else:
                    try:
                        return response.json()
                    except ValueError as exc:
                        raise FetchError("invalid_response", url, "body is not JSON") from exc
            if attempt >= self._max_retries:
                raise last_error
            wait = self._backoff_base * (2**attempt)
            logger.warning("retrying in %.1fs (%s): %s", wait, retry_reason, url)
            self._sleep(wait)
            attempt += 1

    def _throttle(self) -> None:
        if self._last_request_at is None or self._min_interval <= 0:
            return
        remaining = self._min_interval - (self._clock() - self._last_request_at)
        if remaining > 0:
            self._sleep(remaining)

    # -- cache -----------------------------------------------------------------------

    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode()).hexdigest()
        return self._cache_dir / self._today().isoformat() / f"{digest}.json"

    def _read_cache(self, url: str) -> Any | None:
        if not self._use_cache:
            return None
        path = self._cache_path(url)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _write_cache(self, url: str, data: Any) -> None:
        if not self._use_cache:
            return
        path = self._cache_path(url)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            os.replace(tmp, path)
        except OSError as exc:  # a broken cache must never break a run
            logger.warning("could not write cache %s: %s", path, exc)
