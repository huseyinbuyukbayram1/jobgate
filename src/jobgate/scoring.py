"""Stage 4: explainable 0-100 fit score.

The score is a sum of five integer components, each capped by its weight:
role (title vs. target roles), technology (profile technologies found in the posting),
level (junior signals vs. senior signals and years asked), location (place plus work
mode) and compensation (the posting discloses a pay range). Because each component is
rounded on its own, the explanation always adds up to the total.

Scoring never changes a filter decision, and it never calls an LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from jobgate.filters import contains_word, experience_mentions
from jobgate.models import Job
from jobgate.profile import Profile

COMPONENTS = ("role", "technology", "level", "location", "compensation")


class ScoringError(Exception):
    """The weights file is missing or invalid."""


class Weights(BaseModel):
    """Maximum points per component. They must add up to 100."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: int = Field(default=30, ge=0)
    technology: int = Field(default=30, ge=0)
    level: int = Field(default=20, ge=0)
    location: int = Field(default=10, ge=0)
    compensation: int = Field(default=10, ge=0)
    technology_saturation: int = Field(default=3, ge=1)

    @model_validator(mode="after")
    def _sum_to_100(self) -> Weights:
        total = sum(getattr(self, name) for name in COMPONENTS)
        if total != 100:
            raise ValueError(f"weights must add up to 100 (they add up to {total})")
        return self


DEFAULT_WEIGHTS = Weights()


def load_weights(path: Path | str | None) -> Weights:
    if path is None:
        return DEFAULT_WEIGHTS
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        raise ScoringError(f"weights file not found: {path}") from None
    except (OSError, yaml.YAMLError) as exc:
        raise ScoringError(f"cannot read weights file {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ScoringError(f"{path}: top level must be a mapping")
    flat = dict(data.get("weights") or {})
    if "technology_saturation" in data:
        flat["technology_saturation"] = data["technology_saturation"]
    unknown = set(data) - {"weights", "technology_saturation"}
    if unknown:
        raise ScoringError(f"{path}: unknown key(s) {sorted(unknown)}")
    try:
        return Weights.model_validate(flat)
    except ValidationError as exc:
        raise ScoringError(f"invalid weights in {path}: {exc.errors()[0]['msg']}") from exc


@dataclass(frozen=True)
class Score:
    total: int
    parts: dict[str, int]

    def explain(self) -> str:
        """Render e.g. ``72: role 28, technology 20, level 16, location 8`` (zero parts omitted)."""
        shown = ", ".join(f"{name} {points}" for name, points in self.parts.items() if points)
        return f"{self.total}: {shown}" if shown else f"{self.total}"


# -- components -------------------------------------------------------------------------

_SENIOR_TITLE = re.compile(
    r"\b(?:senior|sr\.?|staff|principal|lead|manager|director|head of|vp|architect)\b", re.I
)
_JUNIOR_TITLE = re.compile(
    r"\b(?:junior|jr\.?|graduate|new grad|entry[- ]level|early[- ]career|intern|internship|"
    r"apprentice|working student|trainee)\b|\b(?:engineer|developer) i\b",
    re.I,
)
_JUNIOR_TEXT = re.compile(
    r"entry[- ]level|new grad|recent graduate|early[- ]career|no prior experience", re.I
)
_PAY = re.compile(
    r"(?:\$|€|£|\b(?:usd|eur|gbp|chf)\b)\s?\d{2,3}(?:[,.]\d{3})+"
    r"|\b\d{2,3}k\s?(?:-|–|to)\s?\d{2,3}k\b"
    r"|\b\d{2,3},\d{3}\s?(?:-|–|to)\s?(?:[$€£]\s?)?\d{2,3},\d{3}",
    re.I,
)
_LOCATION_FILLER = re.compile(
    r"\bin[- ]office\b|\bin[- ]person\b|\b(?:remote|anywhere|worldwide|global|hybrid|"
    r"on[- ]?site|flexible|distributed|virtual)\b"
)


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9+#]+", text.lower()))


def _role_ratio(title: str, profile: Profile) -> float:
    title_lower = title.lower()
    prefs = profile.preferences
    if prefs.avoid_roles and contains_word(title_lower, prefs.avoid_roles):
        return 0.0
    title_words = _words(title_lower)
    best = 0.0
    for role in prefs.target_roles:
        tokens = _words(role)
        if not tokens:
            continue
        best = max(best, len(tokens & title_words) / len(tokens))
    return best if best >= 0.5 else 0.0


def _technology_ratio(job: Job, profile: Profile, saturation: int) -> float:
    techs = profile.preferences.technologies
    if not techs:
        return 0.0
    text = f"{job.title}\n{job.description}".lower()
    found = sum(
        1 for t in techs if re.search(rf"(?<![a-z0-9+#]){re.escape(t)}(?![a-z0-9+#])", text)
    )
    return min(1.0, found / min(saturation, len(techs)))


def _level_ratio(job: Job, profile: Profile) -> float:
    if _SENIOR_TITLE.search(job.title):
        return 0.0
    if _JUNIOR_TITLE.search(job.title):
        return 1.0
    if _JUNIOR_TEXT.search(job.description):
        return 0.9
    years = [y for _, y in experience_mentions(job.description)]
    if not years:
        return 0.5
    asked = max(years)
    if asked <= 1:
        return 0.8
    if asked <= profile.max_experience_years:
        return 0.6
    return 0.2


def _work_mode(job: Job) -> str | None:
    text = f"{job.workplace_type or ''} {job.location}".lower()
    if re.search(r"\bhybrid\b", text):
        return "hybrid"
    if re.search(r"\bremote\b|\banywhere\b|\bdistributed\b", text):
        return "remote"
    if re.search(r"on[- ]?site|on site|in[- ]office|in[- ]person", text):
        return "onsite"
    return None


def _location_ratio(job: Job, profile: Profile) -> float:
    location = job.location.lower()
    place_ratio: float
    if contains_word(location, profile.locations.allowed):
        place_ratio = 1.0
    elif not re.search(r"[a-z]", _LOCATION_FILLER.sub(" ", location)):
        place_ratio = 0.5  # empty or only "remote"-like words: region unknown
    else:
        place_ratio = 0.0
    mode = _work_mode(job)
    if mode is None:
        mode_ratio = 0.5
    else:
        mode_ratio = 1.0 if mode in profile.preferences.work_modes else 0.0
    return 0.6 * place_ratio + 0.4 * mode_ratio


def score_job(job: Job, profile: Profile, weights: Weights = DEFAULT_WEIGHTS) -> Score:
    ratios = {
        "role": _role_ratio(job.title, profile),
        "technology": _technology_ratio(job, profile, weights.technology_saturation),
        "level": _level_ratio(job, profile),
        "location": _location_ratio(job, profile),
        "compensation": 1.0 if _PAY.search(job.description) else 0.0,
    }
    parts = {
        name: min(getattr(weights, name), round(getattr(weights, name) * ratios[name]))
        for name in COMPONENTS
    }
    return Score(total=min(100, sum(parts.values())), parts=parts)
