"""Common adapter interface: build a request, fetch it, normalize the answer."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from jobgate.http import FetchError, HttpClient
from jobgate.models import AtsName, Job

logger = logging.getLogger(__name__)


class Adapter(ABC):
    """One adapter per ATS. ``parse`` is pure, so it is tested against fixtures."""

    ats: AtsName

    @abstractmethod
    def request(self, token: str) -> tuple[str, dict[str, str]]:
        """Return the (url, query params) for a company's public job list."""

    @abstractmethod
    def parse(self, raw: Any, company: str) -> list[Job]:
        """Normalize the raw JSON answer into ``Job`` objects."""

    def fetch(self, client: HttpClient, company: str, token: str) -> list[Job]:
        url, params = self.request(token)
        return self.parse(client.get_json(url, params), company)


def build_jobs(
    items: Iterable[Any], make: Callable[[Any], Job | None], ats: str, company: str
) -> list[Job]:
    """Normalize items one by one; a malformed posting is skipped, never fatal."""
    jobs: list[Job] = []
    for item in items:
        try:
            job = make(item)
        except (ValidationError, KeyError, TypeError, ValueError, AttributeError) as exc:
            logger.warning("skipping malformed %s posting for %s: %s", ats, company, exc)
            continue
        if job is not None:
            jobs.append(job)
    return jobs


def invalid_shape(ats: str, detail: str) -> FetchError:
    return FetchError("invalid_response", ats, f"unexpected {ats} response: {detail}")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
