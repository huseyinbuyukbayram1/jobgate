"""One block per rule: at least one posting that passes and one that is stopped."""

import pytest

from jobgate.filters import Verdict, evaluate
from jobgate.models import Job
from jobgate.profile import Profile


def make_profile(**overrides):
    data = {
        "work_authorization": {"regions": ["germany", "eu"]},
        "locations": {"allowed": ["germany", "berlin", "europe", "eu"]},
        "citizenships": ["german"],
        "languages": ["english"],
        "max_experience_years": 2,
        "timezones": {"allowed": ["cet", "utc"]},
    }
    data.update(overrides)
    return Profile.model_validate(data)


def visa_profile():
    """Locations are open, so only the visa rules can decide."""
    return make_profile(locations={"allowed": ["germany", "new york", "london", "austin"]})


def make_job(description="", location="Berlin, Germany", title="Software Engineer"):
    return Job(
        company="Acme",
        title=title,
        location=location,
        description=description,
        url="https://example.com/1",
        ats="greenhouse",
        ats_job_id="1",
    )


def codes(decision):
    return {r.code for r in decision.reasons}


def run(description="", location="Berlin, Germany", profile=None):
    return evaluate(make_job(description, location), profile or make_profile())


# -- overall behaviour ------------------------------------------------------------------


def test_clean_posting_passes_with_no_reasons():
    decision = run("Build web services with Python. Mentoring for graduates.")
    assert decision.verdict is Verdict.PASS
    assert decision.reasons == []


def test_every_reason_has_a_code_and_evidence():
    decision = run("We are unable to sponsor visas.", location="New York, NY")
    reason = decision.reasons[0]
    assert reason.code == "VISA_NO_SPONSORSHIP"
    assert "unable to sponsor" in reason.evidence.lower()


def test_reject_beats_check_and_all_reasons_are_reported():
    decision = run("5+ years of experience required.", location="Remote")
    assert decision.verdict is Verdict.REJECT
    assert codes(decision) == {"EXPERIENCE_TOO_HIGH", "LOCATION_UNCLEAR"}


# -- visa / work permit ------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "We are unable to sponsor visas for this role.",
        "We do not offer visa sponsorship.",
        "No visa sponsorship is available.",
        "Candidates must be able to work without sponsorship.",
        "Sponsorship is not available for this position.",
    ],
)
def test_no_sponsorship_outside_authorized_regions_is_rejected(text):
    decision = run(text, location="New York, NY")
    assert decision.verdict is Verdict.REJECT
    assert "VISA_NO_SPONSORSHIP" in codes(decision)


def test_no_sponsorship_is_irrelevant_where_the_user_may_work():
    decision = run("We are unable to sponsor visas.", location="Berlin, Germany")
    assert decision.verdict is Verdict.PASS


def test_sponsorship_offered_passes():
    p = visa_profile()
    assert run("Visa sponsorship is available.", "New York, NY", p).verdict is Verdict.PASS
    assert run("We sponsor visas for the right people.", "London, UK", p).verdict is Verdict.PASS


def test_conflicting_sponsorship_statements_need_a_check():
    text = "We sponsor visas for strong candidates. We do not offer sponsorship for this role."
    decision = run(text, "New York, NY", visa_profile())
    assert decision.verdict is Verdict.CHECK
    assert codes(decision) == {"SPONSORSHIP_CONFLICT"}


def test_no_sponsorship_with_unknown_location_needs_a_check():
    decision = run("We cannot sponsor visas.", location="")
    assert "SPONSORSHIP_LOCATION_UNKNOWN" in codes(decision)
    assert decision.verdict is Verdict.CHECK


def test_work_authorization_for_a_foreign_country_is_rejected():
    decision = run("You must be authorized to work in the United States.", location="Austin, TX")
    assert decision.verdict is Verdict.REJECT
    assert "WORK_AUTH_REQUIRED" in codes(decision)


def test_work_authorization_for_an_authorized_country_passes():
    decision = run("You must be authorized to work in Germany.")
    assert decision.verdict is Verdict.PASS


def test_generic_work_authorization_sentence_is_not_a_blocker():
    text = "Must be authorized to work in the country where you are applying."
    assert run(text, "Austin, TX", visa_profile()).verdict is Verdict.PASS


# -- citizenship / clearance -------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Applicants must be a US citizen.",
        "Applicants must be a U.S. citizen.",
        "U.S. citizenship is required.",
        "This role is restricted to US persons.",
    ],
)
def test_foreign_citizenship_requirement_is_rejected(text):
    decision = run(text)
    assert decision.verdict is Verdict.REJECT
    assert "CITIZENSHIP_REQUIRED" in codes(decision)


def test_citizenship_the_user_holds_passes():
    assert run("You must be a German citizen.").verdict is Verdict.PASS


def test_diversity_statement_is_not_a_citizenship_requirement():
    assert run("We welcome citizens of all backgrounds.").verdict is Verdict.PASS


@pytest.mark.parametrize(
    "text",
    [
        "Active TS/SCI security clearance required.",
        "You must hold a security clearance.",
        "Ability to obtain a secret clearance is required.",
    ],
)
def test_clearance_requirement_is_rejected(text):
    decision = run(text)
    assert decision.verdict is Verdict.REJECT
    assert "CLEARANCE_REQUIRED" in codes(decision)


def test_clearance_not_required_passes():
    assert run("No security clearance is required.").verdict is Verdict.PASS
    assert run("A security clearance is a plus.").verdict is Verdict.PASS


def test_clearance_holder_passes():
    profile = make_profile(security_clearance=True)
    assert run("Active security clearance required.", profile=profile).verdict is Verdict.PASS


# -- video / assignment ------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Please record a 2-minute video introducing yourself.",
        "Submit a video cover letter with your application.",
        "Applicants must upload a short video.",
    ],
)
def test_video_requirement_is_rejected(text):
    decision = run(text)
    assert decision.verdict is Verdict.REJECT
    assert "VIDEO_REQUIRED" in codes(decision)


def test_video_calls_are_not_a_video_requirement():
    text = "Interviews are held over video call. We will send you a link to the video call."
    assert run(text).verdict is Verdict.PASS


@pytest.mark.parametrize(
    "text",
    [
        "You will complete a take-home assignment.",
        "The process includes a take home coding challenge.",
    ],
)
def test_take_home_assignment_is_rejected(text):
    decision = run(text)
    assert decision.verdict is Verdict.REJECT
    assert "ASSIGNMENT_REQUIRED" in codes(decision)


def test_blocker_settings_can_be_switched_off():
    profile = make_profile(
        blockers={"video_requirement": "ignore", "take_home_assignment": "ignore"}
    )
    text = "Record a video introducing yourself. Then a take-home assignment."
    assert run(text, profile=profile).verdict is Verdict.PASS


# -- years of experience -----------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "5+ years of experience in Python.",
        "3-5 years of professional experience.",
        "At least three years of relevant experience.",
        "Minimum of 4 years' experience with distributed systems.",
    ],
)
def test_experience_above_threshold_is_rejected(text):
    decision = run(text)
    assert decision.verdict is Verdict.REJECT
    assert "EXPERIENCE_TOO_HIGH" in codes(decision)


@pytest.mark.parametrize(
    "text",
    [
        "0-2 years of experience.",
        "1-2 years of experience with Python.",
        "2 years of experience.",
        "No prior experience required.",
        "5+ years of experience is a plus.",
        "The company has 10 years of history.",
        "Preferred: 4 years of experience.",
    ],
)
def test_experience_within_threshold_or_optional_passes(text):
    assert run(text).verdict is Verdict.PASS


def test_experience_with_degree_alternative_needs_a_check():
    text = "4 years of experience or a Master's degree in lieu of experience."
    decision = run(text)
    assert decision.verdict is Verdict.CHECK
    assert codes(decision) == {"EXPERIENCE_AMBIGUOUS"}


def test_threshold_comes_from_the_profile():
    profile = make_profile(max_experience_years=5)
    assert run("4 years of experience.", profile=profile).verdict is Verdict.PASS


# -- location ----------------------------------------------------------------------------


@pytest.mark.parametrize("location", ["San Francisco, CA", "Remote - US", "Stockholm, Sweden"])
def test_location_outside_profile_is_rejected(location):
    decision = run(location=location)
    assert decision.verdict is Verdict.REJECT
    assert "LOCATION_OUTSIDE_PROFILE" in codes(decision)


@pytest.mark.parametrize(
    "location", ["Berlin, Germany", "Remote - Europe", "New York; Berlin", "EU (remote)"]
)
def test_location_inside_profile_passes(location):
    assert run(location=location).verdict is Verdict.PASS


@pytest.mark.parametrize("location", ["Remote", "", "Anywhere", "Remote (flexible)"])
def test_unclear_location_needs_a_check(location):
    decision = run(location=location)
    assert decision.verdict is Verdict.CHECK
    assert codes(decision) == {"LOCATION_UNCLEAR"}


def test_location_match_uses_whole_words():
    # "eu" is allowed, but must not match inside "Neuchatel"
    decision = run(location="Neuchatel, Switzerland")
    assert "LOCATION_OUTSIDE_PROFILE" in codes(decision)


# -- time zone ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "You must work Pacific Time hours.",
        "Overlap with EST working hours is required.",
        "Team members work PST business hours.",
    ],
)
def test_foreign_timezone_requirement_is_rejected(text):
    decision = run(text)
    assert decision.verdict is Verdict.REJECT
    assert "TIMEZONE_OUTSIDE_PROFILE" in codes(decision)


@pytest.mark.parametrize(
    "text",
    [
        "Overlap with CET working hours is required.",
        "We are flexible about time zones.",
        "Our central office is open for interest.",
    ],
)
def test_compatible_or_absent_timezone_passes(text):
    assert run(text).verdict is Verdict.PASS


# -- language ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Fluent German is required.",
        "Fluency in French and English is required.",
        "You must speak Spanish.",
    ],
)
def test_required_language_missing_from_profile_is_rejected(text):
    decision = run(text)
    assert decision.verdict is Verdict.REJECT
    assert "LANGUAGE_NOT_IN_PROFILE" in codes(decision)


@pytest.mark.parametrize(
    "text",
    [
        "Fluent English is required.",
        "German is a plus.",
        "Fluent in French or English.",
        "Native-level French is preferred.",
    ],
)
def test_language_in_profile_or_optional_passes(text):
    assert run(text).verdict is Verdict.PASS
