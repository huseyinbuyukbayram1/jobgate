"""The user's profile (profile.yaml): what the filter and the scorer compare postings to."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

BlockerMode = Literal["reject", "ignore"]
WorkMode = Literal["remote", "hybrid", "onsite"]
StudentStatus = Literal["graduated", "enrolled"]


class ProfileError(Exception):
    """The profile file is missing, unreadable or invalid."""


def _lower(values: list[str]) -> list[str]:
    return [v.strip().lower() for v in values if v and v.strip()]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkAuthorization(_Strict):
    regions: list[str] = Field(min_length=1)

    _norm = field_validator("regions")(_lower)


class Locations(_Strict):
    allowed: list[str] = Field(min_length=1)

    _norm = field_validator("allowed")(_lower)


class Timezones(_Strict):
    allowed: list[str] = Field(default_factory=list)

    _norm = field_validator("allowed")(_lower)


class Blockers(_Strict):
    video_requirement: BlockerMode = "reject"
    take_home_assignment: BlockerMode = "reject"


class Preferences(_Strict):
    """What the scorer rewards. All words are matched case-insensitively."""

    target_roles: list[str] = Field(default_factory=list)  # phrases matched against the title
    avoid_roles: list[str] = Field(default_factory=list)  # a hit in the title scores role 0
    technologies: list[str] = Field(default_factory=list)  # matched in title and description
    work_modes: list[WorkMode] = Field(default_factory=lambda: ["remote", "hybrid"])

    _norm = field_validator("target_roles", "avoid_roles", "technologies")(_lower)


class Profile(_Strict):
    work_authorization: WorkAuthorization
    locations: Locations
    citizenships: list[str] = Field(default_factory=list)
    security_clearance: bool = False
    max_experience_years: int = Field(default=2, ge=0)
    languages: list[str] = Field(default_factory=lambda: ["english"])
    timezones: Timezones = Field(default_factory=Timezones)
    blockers: Blockers = Field(default_factory=Blockers)
    preferences: Preferences = Field(default_factory=Preferences)
    # Optional. Without them the student-status and graduation-year rules do nothing.
    graduation_year: int | None = Field(default=None, ge=1990, le=2100)
    student_status: StudentStatus | None = None

    _norm = field_validator("citizenships", "languages")(_lower)

    @field_validator("student_status", mode="before")
    @classmethod
    def _status_case(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


def load_profile(path: Path | str) -> Profile:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ProfileError(f"profile file not found: {path}") from None
    except OSError as exc:
        raise ProfileError(f"cannot read profile file {path}: {exc}") from exc
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise ProfileError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ProfileError(f"{path}: top level must be a mapping")
    try:
        return Profile.model_validate(data)
    except ValidationError as exc:
        lines = [f"  - {'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
        raise ProfileError(f"invalid profile {path}:\n" + "\n".join(lines)) from exc
