"""Stage 4: explainable 0-100 fit score.

The score is a sum of five integer components, each capped by its weight:
role (title vs. target roles, see ``_role_match``), technology (profile technologies found
in the posting), level (junior signals vs. senior signals and years asked), location (place
plus work mode) and compensation (the posting discloses a pay range). Because each component is
rounded on its own, the explanation always adds up to the total.

Scoring never changes a filter decision, and it never calls an LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from jobgate.filters import contains_word, experience_mentions
from jobgate.models import Job
from jobgate.profile import Profile

COMPONENTS = ("role", "technology", "level", "location", "compensation")

# Other ways a title can name a role. Keys are the canonical phrase (normally one of your
# target roles), values are alternatives that are rewritten to it before matching. The same
# list is in scoring.example.yaml (a test keeps the two equal).
DEFAULT_ROLE_SYNONYMS: dict[str, list[str]] = {
    "software engineer": [
        "member of technical staff",
        "software developer",
        "software development engineer",
        "software dev engineer",
        "developer",
        "swe",
        "sde",
    ],
    "backend engineer": ["back end engineer", "backend developer", "back end developer"],
    "frontend engineer": ["front end engineer", "frontend developer", "front end developer"],
    "machine learning engineer": ["ml engineer", "mle", "machine learning developer"],
}


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
    role_synonyms: dict[str, list[str]] = Field(
        default_factory=lambda: {k: list(v) for k, v in DEFAULT_ROLE_SYNONYMS.items()}
    )

    @field_validator("role_synonyms")
    @classmethod
    def _clean_synonyms(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        cleaned: dict[str, list[str]] = {}
        for role, phrases in value.items():
            key = " ".join(_tokens(role))
            if not key:
                raise ValueError("role_synonyms: a role name must not be empty")
            cleaned[key] = [p for p in (" ".join(_tokens(x)) for x in phrases) if p]
        return cleaned

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
    if "role_synonyms" in data:
        synonyms = data["role_synonyms"]
        if not isinstance(synonyms, dict) or not all(
            isinstance(v, list) and all(isinstance(x, str) for x in v) for v in synonyms.values()
        ):
            raise ScoringError(
                f"{path}: role_synonyms must map a role to a list of phrases, "
                "for example  software engineer: [swe, developer]"
            )
        flat["role_synonyms"] = synonyms
    unknown = set(data) - {"weights", "technology_saturation", "role_synonyms"}
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
    role_match: str = ""  # which role match produced the role points, "" if none

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


# -- role matching ----------------------------------------------------------------------
#
# The title is normalised (lower case, punctuation removed, "engineering"/"engineers" ->
# "engineer", synonyms rewritten to their canonical phrase) and split at " - ", commas and
# brackets into a head ("Software Engineer") and later parts (a team or a location). Then
# each target role is tried, and the best tier wins:
#   whole phrase in the head ........ 1.0     "Software Engineer, Payments"
#   all its words in the head ....... 0.9     "Software Quality Engineer"
#   whole phrase in a later part .... 0.8     "Platform Lead - Software Engineer"
#   at least half its words in head . the share of words, at most 0.75   "Backend Engineer"
# Words in a team name (the later parts) never count as a partial match.

_STEMS = {"engineering": "engineer", "engineers": "engineer", "developers": "developer"}
# "developer relations", "developer platform" ... are not developer jobs: no synonym there.
_SYNONYM_BLOCKERS = {
    "relations", "advocate", "advocacy", "experience", "evangelist", "success",
    "platform", "productivity", "tooling", "tools",
}  # fmt: skip
# "Engineering Manager" is a management job, not an engineer title: "engineering" stays as is.
_NOT_ENGINEER = {
    "manager", "director", "lead", "head", "management", "leadership", "team", "operations", "ops",
}  # fmt: skip
_SPLIT = re.compile(r"\s[-\u2013\u2014|:]\s|[,;|:()\[\]]")
PARTIAL_CAP = 0.75


def _tokens(text: str) -> list[str]:
    raw = re.findall(r"[a-z0-9+#]+", text.lower())
    return [
        t
        if t == "engineering" and raw[i + 1 : i + 2] and raw[i + 1] in _NOT_ENGINEER
        else _STEMS.get(t, t)
        for i, t in enumerate(raw)
    ]


@lru_cache(maxsize=8)
def _compile_synonyms(items: tuple[tuple[str, tuple[str, ...]], ...]) -> list[tuple]:
    """(phrase tokens, canonical tokens, canonical text), longest phrase first."""
    compiled = []
    for canonical, phrases in items:
        target = tuple(_tokens(canonical))
        for phrase in phrases:
            tokens = tuple(_tokens(phrase))
            if tokens and target:
                compiled.append((tokens, target, canonical))
    compiled.sort(key=lambda c: (-len(c[0]), c[0]))
    return compiled


def _rewrite(tokens: list[str], compiled: list[tuple], applied: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(tokens):
        for phrase, target, _canonical in compiled:
            end = i + len(phrase)
            if tuple(tokens[i:end]) == phrase and not (
                end < len(tokens) and tokens[end] in _SYNONYM_BLOCKERS
            ):
                out.extend(target)
                applied.append(" ".join(phrase))
                i = end
                break
        else:
            out.append(tokens[i])
            i += 1
    return out


def _contains_sequence(haystack: list[str], needle: list[str]) -> bool:
    n = len(needle)
    return n > 0 and any(haystack[i : i + n] == needle for i in range(len(haystack) - n + 1))


def _best_match(segments: list[list[str]], roles: list[tuple[str, list[str]]]) -> tuple[float, str]:
    head, later = (segments[0] if segments else []), segments[1:]
    best: tuple[float, str] = (0.0, "")
    for name, tokens in roles:
        wanted = set(tokens)
        if not wanted:
            continue
        if _contains_sequence(head, tokens):
            found = (1.0, f'phrase "{name}"')
        elif wanted <= set(head):
            found = (0.9, f'all words of "{name}"')
        elif any(_contains_sequence(seg, tokens) for seg in later):
            found = (0.8, f'phrase "{name}" later in the title')
        else:
            shared = len(wanted & set(head))
            if shared / len(wanted) < 0.5:
                continue
            found = (
                min(shared / len(wanted), PARTIAL_CAP),
                f'part of "{name}" ({shared} of {len(wanted)} words)',
            )
        if found[0] > best[0]:
            best = found
    return best


def _role_match(title: str, profile: Profile, weights: Weights) -> tuple[float, str]:
    """Role ratio (0-1) and a short text saying which match counted."""
    prefs = profile.preferences
    lowered = title.lower()
    for word in prefs.avoid_roles:
        if contains_word(lowered, [word]):
            return 0.0, f'avoided word "{word}"'
    segments = [_tokens(part) for part in _SPLIT.split(lowered) if part.strip()]
    plain = [(role, _tokens(role)) for role in prefs.target_roles]
    ratio, text = _best_match(segments, plain)
    compiled = _compile_synonyms(
        tuple((k, tuple(v)) for k, v in sorted(weights.role_synonyms.items()))
    )
    if compiled:
        applied: list[str] = []
        # synonyms apply to the head only: later parts are teams and places, not the role
        rewritten = [
            _rewrite(seg, compiled, applied) if i == 0 else seg for i, seg in enumerate(segments)
        ]
        roles = [(role, _rewrite(tokens, compiled, [])) for role, tokens in plain]
        syn_ratio, syn_text = _best_match(rewritten, roles)
        if syn_ratio > ratio:
            return syn_ratio, f'{syn_text} via "{", ".join(dict.fromkeys(applied))}"'
    return ratio, text


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
    role_ratio, role_match = _role_match(job.title, profile, weights)
    ratios = {
        "role": role_ratio,
        "technology": _technology_ratio(job, profile, weights.technology_saturation),
        "level": _level_ratio(job, profile),
        "location": _location_ratio(job, profile),
        "compensation": 1.0 if _PAY.search(job.description) else 0.0,
    }
    parts = {
        name: min(getattr(weights, name), round(getattr(weights, name) * ratios[name]))
        for name in COMPONENTS
    }
    return Score(total=min(100, sum(parts.values())), parts=parts, role_match=role_match)
