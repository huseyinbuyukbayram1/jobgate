"""Greenhouse Job Board API (public, no authentication)."""

from __future__ import annotations

from typing import Any

from jobgate.adapters.base import Adapter, build_jobs, invalid_shape, parse_iso
from jobgate.htmltext import html_to_text
from jobgate.models import Job

BASE_URL = "https://boards-api.greenhouse.io/v1/boards"


class GreenhouseAdapter(Adapter):
    ats = "greenhouse"

    def request(self, token: str) -> tuple[str, dict[str, str]]:
        # content=true is what puts the description in the list response.
        return f"{BASE_URL}/{token}/jobs", {"content": "true"}

    def parse(self, raw: Any, company: str) -> list[Job]:
        if not isinstance(raw, dict) or not isinstance(raw.get("jobs"), list):
            raise invalid_shape(self.ats, "expected an object with a 'jobs' list")

        def make(item: dict[str, Any]) -> Job:
            location = item.get("location") or {}
            return Job(
                company=company,
                title=(item.get("title") or "").strip(),
                location=(location.get("name") or "").strip(),
                description=html_to_text(item.get("content")),
                url=item["absolute_url"],
                # first_published is not in the documented list response but is
                # present in live answers; updated_at is the documented fallback.
                posted_at=parse_iso(item.get("first_published") or item.get("updated_at")),
                ats=self.ats,
                ats_job_id=str(item["id"]),
            )

        return build_jobs(raw["jobs"], make, self.ats, company)
