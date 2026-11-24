"""Ashby public job posting API (no authentication)."""

from __future__ import annotations

from typing import Any

from jobgate.adapters.base import Adapter, build_jobs, invalid_shape, parse_iso
from jobgate.htmltext import html_to_text
from jobgate.models import Job

BASE_URL = "https://api.ashbyhq.com/posting-api/job-board"


class AshbyAdapter(Adapter):
    ats = "ashby"

    def request(self, token: str) -> tuple[str, dict[str, str]]:
        return f"{BASE_URL}/{token}", {"includeCompensation": "true"}

    def parse(self, raw: Any, company: str) -> list[Job]:
        if not isinstance(raw, dict) or not isinstance(raw.get("jobs"), list):
            raise invalid_shape(self.ats, "expected an object with a 'jobs' list")

        def make(item: dict[str, Any]) -> Job | None:
            if item.get("isListed") is False:
                return None
            url = item["jobUrl"]
            # No id field is documented; live answers carry one, else use the URL tail.
            job_id = item.get("id") or url.rstrip("/").rsplit("/", 1)[-1]
            return Job(
                company=company,
                title=(item.get("title") or "").strip(),
                location=(item.get("location") or "").strip(),
                description=item.get("descriptionPlain")
                or html_to_text(item.get("descriptionHtml")),
                url=url,
                posted_at=parse_iso(item.get("publishedAt")),
                ats=self.ats,
                ats_job_id=str(job_id),
                workplace_type=item.get("workplaceType") or None,
            )

        return build_jobs(raw["jobs"], make, self.ats, company)
