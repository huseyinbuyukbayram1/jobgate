"""Lever Postings API (public, no authentication)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from jobgate.adapters.base import Adapter, build_jobs, invalid_shape
from jobgate.htmltext import html_to_text
from jobgate.models import Job

BASE_URL = "https://api.lever.co/v0/postings"


class LeverAdapter(Adapter):
    ats = "lever"

    def request(self, token: str) -> tuple[str, dict[str, str]]:
        return f"{BASE_URL}/{token}", {"mode": "json"}

    def parse(self, raw: Any, company: str) -> list[Job]:
        if not isinstance(raw, list):
            raise invalid_shape(self.ats, "expected a list of postings")

        def make(item: dict[str, Any]) -> Job:
            categories = item.get("categories") or {}
            location = categories.get("location") or ", ".join(categories.get("allLocations") or [])
            parts = [item.get("descriptionPlain") or html_to_text(item.get("description"))]
            for section in item.get("lists") or []:
                parts.append(f"{section.get('text', '')}\n{html_to_text(section.get('content'))}")
            parts.append(item.get("additionalPlain") or html_to_text(item.get("additional")))
            created = item.get("createdAt")  # live field, not in the documented table
            return Job(
                company=company,
                title=(item.get("text") or "").strip(),
                location=location.strip(),
                description="\n".join(p.strip() for p in parts if p and p.strip()),
                url=item["hostedUrl"],
                posted_at=(
                    datetime.fromtimestamp(created / 1000, UTC) if created is not None else None
                ),
                ats=self.ats,
                ats_job_id=str(item["id"]),
                workplace_type=item.get("workplaceType") or None,
            )

        return build_jobs(raw, make, self.ats, company)
