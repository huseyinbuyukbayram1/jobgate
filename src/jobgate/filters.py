"""Stage 3: rule-based blocker filter.

Every rule looks at one posting and the user's profile and returns zero or more
``Reason`` objects, each with a stable code, a verdict and the sentence that caused it.
The overall verdict is the strictest one: any REJECT wins, otherwise any CHECK, else PASS.

Design notes
- A hard blocker (the posting clearly cannot work for this profile) is REJECT.
- Unclear or contradicting wording is CHECK, so a human looks at it; the filter prefers
  asking over silently throwing a posting away.
- No LLM is involved here. Rules are plain regular expressions on single sentences.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from jobgate.models import Job
from jobgate.profile import Profile


class Verdict(StrEnum):
    PASS = "pass"
    CHECK = "check"
    REJECT = "reject"


@dataclass(frozen=True)
class Reason:
    code: str
    verdict: Verdict
    evidence: str


@dataclass
class Decision:
    verdict: Verdict
    reasons: list[Reason] = field(default_factory=list)

    @property
    def codes(self) -> list[str]:
        return [r.code for r in self.reasons]


# -- text helpers -----------------------------------------------------------------------

_SOFT = re.compile(
    r"\b(?:plus|preferred|prefer|nice[- ]to[- ]have|bonus|advantage|desirable|asset|"
    r"beneficial|ideally|optional|a plus)\b"
)


def sentences(text: str) -> list[str]:
    """Split posting text into sentences (one per line break or sentence end)."""
    text = re.sub(r"\b([A-Za-z])\.([A-Za-z])\.", r"\1\2", text)  # U.S. -> US
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip() for p in parts if p and p.strip()]


def contains_word(text: str, words: list[str]) -> bool:
    return any(re.search(rf"(?<![a-z0-9]){re.escape(w)}(?![a-z0-9])", text) for w in words)


def snippet(sentence: str, limit: int = 200) -> str:
    sentence = " ".join(sentence.split())
    return sentence if len(sentence) <= limit else sentence[: limit - 1] + "…"


def is_soft(sentence_lower: str) -> bool:
    return bool(_SOFT.search(sentence_lower))


# -- visa / work permit -----------------------------------------------------------------

_NO_SPONSOR = [
    re.compile(r"\b(?:unable|cannot|can't|won't|don't|doesn't|not|no)\b[^.]{0,40}?\bsponsor"),
    re.compile(r"\bwithout\b[^.]{0,25}?\bsponsor"),
    re.compile(r"\bsponsor\w*\b[^.]{0,25}?\b(?:not|isn't|unavailable)\b"),
]
_SPONSOR_WORD = re.compile(r"\bsponsor")
# "sponsor" used in other senses: export licences, benefits, executive sponsors, events
_NOT_VISA_SPONSOR = re.compile(
    r"\bexport\b|employer[- ]sponsored|\bexecutive\b|\bengagement\b|\bbin sponsor|"
    r"\bsponsored (?:group|plan|health|benefit)|\bsponsor(?:ship)? (?:program|event|conference)"
)
_REQUIRE_SPONSOR = re.compile(r"\brequire\w*\b[^.]{0,30}\bsponsor")
_WORK_AUTH = re.compile(
    r"\b(?:authori[sz]ed|eligible|permitted|entitled|legally (?:able|allowed)|right)\s+"
    r"to\s+work\s+(?:legally\s+)?in\s+(?:the\s+)?([^.,;]{2,50})"
)
_KNOWN_PLACES = [
    "united states", "usa", "us", "united kingdom", "uk", "england", "canada", "australia",
    "new zealand", "india", "singapore", "japan", "china", "brazil", "mexico", "israel",
    "uae", "united arab emirates", "switzerland", "norway", "sweden", "denmark", "finland",
    "poland", "france", "germany", "italy", "spain", "portugal", "netherlands", "ireland",
    "belgium", "austria", "czech republic", "romania", "turkey", "argentina", "colombia",
    "south africa", "nigeria", "kenya", "egypt", "korea", "philippines", "vietnam",
]  # fmt: skip


def _is_no_sponsor(sentence_lower: str) -> bool:
    return any(p.search(sentence_lower) for p in _NO_SPONSOR)


def rule_visa(job: Job, profile: Profile) -> list[Reason]:
    regions = profile.work_authorization.regions
    location = job.location.lower()
    location_authorized = contains_word(location, regions)
    negative: list[str] = []
    positive: list[str] = []
    reasons: list[Reason] = []
    for sentence in sentences(job.description):
        lower = sentence.lower()
        if _SPONSOR_WORD.search(lower) and not _NOT_VISA_SPONSOR.search(lower):
            if _is_no_sponsor(lower):
                negative.append(sentence)
            elif not _REQUIRE_SPONSOR.search(lower):
                positive.append(sentence)
        match = _WORK_AUTH.search(lower)
        if match:
            place = match.group(1)
            foreign = contains_word(place, _KNOWN_PLACES) and not contains_word(place, regions)
            if foreign:
                reasons.append(Reason("WORK_AUTH_REQUIRED", Verdict.REJECT, snippet(sentence)))
    if negative and not location_authorized:
        if positive:
            reasons.append(Reason("SPONSORSHIP_CONFLICT", Verdict.CHECK, snippet(negative[0])))
        elif _location_unclear(job.location) or contains_word(location, profile.locations.allowed):
            # The user would work there but nothing proves they may: ask, do not reject.
            reasons.append(
                Reason("SPONSORSHIP_LOCATION_UNKNOWN", Verdict.CHECK, snippet(negative[0]))
            )
        else:
            reasons.append(Reason("VISA_NO_SPONSORSHIP", Verdict.REJECT, snippet(negative[0])))
    return reasons


# -- citizenship / clearance ------------------------------------------------------------

_CITIZEN = [
    re.compile(r"\b(?:must|need to|required to)\s+(?:be|hold)\b[^.]{0,40}\bcitizen"),
    re.compile(r"\bcitizenship\b[^.]{0,30}\b(?:required|mandatory|needed)"),
    re.compile(r"\b(?:requires?|requiring)\b[^.]{0,30}\bcitizenship"),
    re.compile(r"\bus persons?\b"),
    re.compile(r"\b(?:only|restricted to|limited to)\b[^.]{0,30}\bcitizens"),
]
_CLEARANCE = re.compile(r"\b(?:security clearance|ts/sci|top secret|clearance)\b")
_CLEARANCE_NEEDED = re.compile(
    r"\b(?:required|must|active|obtain|eligib\w+|hold|possess|need\w*|mandatory)\b"
)
_CLEARANCE_NEGATED = re.compile(
    r"\b(?:no|not|without)\b[^.]{0,25}clearance|clearance[^.]{0,25}\b(?:not|isn't)\b"
)


def rule_citizenship(job: Job, profile: Profile) -> list[Reason]:
    reasons: list[Reason] = []
    for sentence in sentences(job.description):
        lower = sentence.lower()
        if is_soft(lower):
            continue
        if (
            _CLEARANCE.search(lower)
            and _CLEARANCE_NEEDED.search(lower)
            and not _CLEARANCE_NEGATED.search(lower)
        ):
            if not profile.security_clearance:
                reasons.append(Reason("CLEARANCE_REQUIRED", Verdict.REJECT, snippet(sentence)))
            continue
        if any(p.search(lower) for p in _CITIZEN):
            if not contains_word(lower, profile.citizenships):
                reasons.append(Reason("CITIZENSHIP_REQUIRED", Verdict.REJECT, snippet(sentence)))
    return reasons


# -- video / take-home assignment -------------------------------------------------------

_NOT_CALL = r"(?!\s*(?:call|interview|conferenc|meeting|chat|platform|streaming))"
_VIDEO = [
    re.compile(
        r"\b(?:record|submit|upload|include|attach|send|create|make|film|share)\w*\b"
        rf"[^.]{{0,60}}\bvideo\b{_NOT_CALL}"
    ),
    re.compile(r"\bvideo (?:cover letter|introduction|intro|application|resume|cv|pitch|essay)\b"),
    re.compile(r"\b(?:one-?way|asynchronous|pre-?recorded) video\b"),
]
_ASSIGNMENT = re.compile(
    r"\btake[- ]home\b[^.]{0,30}\b(?:assignment|assessment|project|challenge|test|task|exercise)"
    r"|\bhomework assignment\b"
)


def rule_video_and_assignment(job: Job, profile: Profile) -> list[Reason]:
    reasons: list[Reason] = []
    for sentence in sentences(job.description):
        lower = sentence.lower()
        if is_soft(lower):
            continue
        if profile.blockers.video_requirement == "reject" and any(p.search(lower) for p in _VIDEO):
            reasons.append(Reason("VIDEO_REQUIRED", Verdict.REJECT, snippet(sentence)))
        if profile.blockers.take_home_assignment == "reject" and _ASSIGNMENT.search(lower):
            reasons.append(Reason("ASSIGNMENT_REQUIRED", Verdict.REJECT, snippet(sentence)))
    return reasons


# -- years of experience ----------------------------------------------------------------

_NUMBER_WORDS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
}  # fmt: skip
_NUMBER_WORD = re.compile(
    rf"\b({'|'.join(_NUMBER_WORDS)})\b(?=\s+(?:or more\s+)?(?:years?|yrs?)\b)"
)
_YEARS = re.compile(
    r"(\d{1,2})\s*(?:\+|plus)?\s*(?:(?:-|–|to)\s*(\d{1,2}))?\s*\+?\s*(?:or more\s+)?"
    r"(?:years?|yrs?)\b"
)
_DEGREE_ALTERNATIVE = re.compile(
    r"\b(?:or|in lieu of)\b[^.]{0,40}\b(?:degree|master|phd|bachelor|equivalent)"
    r"|\b(?:degree|master|phd)\b[^.]{0,40}\b(?:or|in lieu)\b"
)


def experience_mentions(text: str) -> list[tuple[str, int]]:
    """(sentence, required years) for every non-optional sentence that asks for years.

    Public because the scorer reads the same numbers. For a range such as "3-5 years" the
    lower bound counts; sentences that only list years as a plus or preference are skipped.
    """
    mentions: list[tuple[str, int]] = []
    for sentence in sentences(text):
        lower = sentence.lower()
        if "experience" not in lower or is_soft(lower):
            continue
        lower = _NUMBER_WORD.sub(lambda m: _NUMBER_WORDS[m.group(1)], lower)
        bounds = [int(m.group(1)) for m in _YEARS.finditer(lower)]
        if bounds:
            mentions.append((sentence, max(bounds)))
    return mentions


def rule_experience(job: Job, profile: Profile) -> list[Reason]:
    reasons: list[Reason] = []
    for sentence, years in experience_mentions(job.description):
        if years <= profile.max_experience_years:
            continue
        if _DEGREE_ALTERNATIVE.search(sentence.lower()):
            reasons.append(Reason("EXPERIENCE_AMBIGUOUS", Verdict.CHECK, snippet(sentence)))
        else:
            reasons.append(Reason("EXPERIENCE_TOO_HIGH", Verdict.REJECT, snippet(sentence)))
    return reasons


# -- location ---------------------------------------------------------------------------

_LOCATION_FILLER = re.compile(
    r"\bin[- ]office\b|\bin[- ]person\b|"
    r"\b(?:remote|anywhere|worldwide|global|hybrid|on[- ]?site|flexible|distributed|home|"
    r"wfh|work|from|based|office|virtual|multiple|locations?|various|tbd|n/a)\b"
)


def _location_unclear(location: str) -> bool:
    """True for an empty location or one that says only 'remote'-like things."""
    leftover = _LOCATION_FILLER.sub(" ", location.lower())
    return not re.search(r"[a-z]", leftover)


def rule_location(job: Job, profile: Profile) -> list[Reason]:
    if _location_unclear(job.location):
        return [Reason("LOCATION_UNCLEAR", Verdict.CHECK, snippet(job.location or "(empty)"))]
    if contains_word(job.location.lower(), profile.locations.allowed):
        return []
    return [Reason("LOCATION_OUTSIDE_PROFILE", Verdict.REJECT, snippet(job.location))]


# -- time zone --------------------------------------------------------------------------

_TZ_CONTEXT = re.compile(
    r"\b(?:overlap|working hours|business hours|work hours|time ?zones?|core hours|hours|"
    r"availability|align\w*)\b"
)
_FOREIGN_TZ = re.compile(
    r"\b(?:PST|PDT|PT|EST|EDT|ET|CST|CDT|CT|MST|MDT|MT|IST|AEST|JST|SGT)\b"
    r"|\b(?:Pacific|Eastern|Central|Mountain)\s+(?:Standard\s+|Daylight\s+)?Time\b"
)


def rule_timezone(job: Job, profile: Profile) -> list[Reason]:
    reasons: list[Reason] = []
    for sentence in sentences(job.description):
        lower = sentence.lower()
        if not _TZ_CONTEXT.search(lower) or not _FOREIGN_TZ.search(sentence):
            continue
        if contains_word(lower, profile.timezones.allowed):
            continue
        reasons.append(Reason("TIMEZONE_OUTSIDE_PROFILE", Verdict.REJECT, snippet(sentence)))
    return reasons


# -- language ---------------------------------------------------------------------------

_LANGUAGES = {
    "english": ["english"],
    "german": ["german", "deutsch"],
    "french": ["french", "français", "francais"],
    "spanish": ["spanish", "español", "espanol"],
    "italian": ["italian"],
    "dutch": ["dutch", "nederlands"],
    "portuguese": ["portuguese"],
    "japanese": ["japanese"],
    "mandarin": ["mandarin", "chinese"],
    "korean": ["korean"],
    "arabic": ["arabic"],
    "hindi": ["hindi"],
    "russian": ["russian"],
    "polish": ["polish"],
    "swedish": ["swedish"],
    "turkish": ["turkish"],
}
_LANGUAGE_NEEDED = re.compile(
    r"\b(?:fluen\w+|native|proficien\w+|business[- ]level|written and spoken|"
    r"spoken and written|c1|c2|must speak|must be able to speak|required|mandatory|"
    r"excellent command|strong command|command of)\b"
)
_ALTERNATIVE = re.compile(r"\b(?:or|either)\b|and/or")


def _languages_in(sentence_lower: str) -> set[str]:
    return {
        name
        for name, aliases in _LANGUAGES.items()
        if any(re.search(rf"(?<![a-z]){a}(?![a-z])", sentence_lower) for a in aliases)
    }


def rule_language(job: Job, profile: Profile) -> list[Reason]:
    known = set(profile.languages)
    for name, aliases in _LANGUAGES.items():  # a profile may use an alias such as "deutsch"
        if known & set(aliases):
            known.add(name)
    reasons: list[Reason] = []
    for sentence in sentences(job.description):
        lower = sentence.lower()
        if is_soft(lower) or not _LANGUAGE_NEEDED.search(lower):
            continue
        mentioned = _languages_in(lower)
        if not mentioned:
            continue
        if _ALTERNATIVE.search(lower):
            missing = mentioned if not (mentioned & known) else set()
        else:
            missing = mentioned - known
        if missing:
            reasons.append(Reason("LANGUAGE_NOT_IN_PROFILE", Verdict.REJECT, snippet(sentence)))
    return reasons


# -- orchestration ----------------------------------------------------------------------

RULES: list[Callable[[Job, Profile], list[Reason]]] = [
    rule_visa,
    rule_citizenship,
    rule_video_and_assignment,
    rule_experience,
    rule_location,
    rule_timezone,
    rule_language,
]


def evaluate(job: Job, profile: Profile) -> Decision:
    reasons = [reason for rule in RULES for reason in rule(job, profile)]
    if any(r.verdict is Verdict.REJECT for r in reasons):
        verdict = Verdict.REJECT
    elif reasons:
        verdict = Verdict.CHECK
    else:
        verdict = Verdict.PASS
    return Decision(verdict, reasons)
