"""Normalized data models shared by every pipeline stage."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

AtsName = Literal["greenhouse", "lever", "ashby"]


class Job(BaseModel):
    """One public job posting, independent of the ATS it came from."""

    model_config = ConfigDict(frozen=True)

    company: str = Field(min_length=1)
    title: str = Field(min_length=1)
    location: str = ""
    description: str = ""
    url: str = Field(min_length=1)
    posted_at: datetime | None = None
    ats: AtsName
    ats_job_id: str = Field(min_length=1)
    workplace_type: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def key(self) -> str:
        """Stable identity used for de-duplication across runs."""
        return f"{self.ats}:{self.company}:{self.ats_job_id}"
