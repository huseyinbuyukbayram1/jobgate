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


# -- regressions found on real postings ----------------------------------------------------


def test_export_control_wording_is_not_a_visa_blocker():
    text = (
        "Any offer may be conditioned on your authorization to receive software controlled "
        "under US export laws without sponsorship for an export license."
    )
    assert run(text, location="New York, NY", profile=visa_profile()).verdict is Verdict.PASS


def test_sponsored_benefits_and_executive_sponsors_are_not_visa_sponsorship():
    text = "100% employer-sponsored group medical plan. Build executive sponsorship programs."
    assert run(text).verdict is Verdict.PASS
    text += " We do not offer visa sponsorship."
    assert "VISA_NO_SPONSORSHIP" in run(text, "New York, NY").codes


def test_conflicting_sponsorship_is_harmless_where_the_user_may_work():
    text = "We sponsor visas for strong candidates. We do not offer sponsorship for this role."
    assert run(text, location="Berlin, Germany").verdict is Verdict.PASS


def test_no_sponsorship_in_a_region_that_is_allowed_but_not_authorized_needs_a_check():
    # "Europe" is somewhere the user would work, but it does not prove their right to work
    decision = run("We cannot sponsor visas.", location="Remote - Europe")
    assert decision.verdict is Verdict.CHECK
    assert codes(decision) == {"SPONSORSHIP_LOCATION_UNKNOWN"}


def test_fluently_counts_as_a_language_requirement():
    assert run("You can speak English and French fluently.").verdict is Verdict.REJECT


@pytest.mark.parametrize("location", ["In-Office", "Hybrid", "In person"])
def test_workplace_mode_words_alone_are_an_unclear_location(location):
    assert codes(run(location=location)) == {"LOCATION_UNCLEAR"}


# -- seniority in the title -------------------------------------------------------------


def run_title(title, description=""):
    return evaluate(make_job(description, title=title), make_profile())


@pytest.mark.parametrize(
    "title",
    [
        "Senior Partner Solutions Architect (Pan-EMEA GSI)",
        "Senior Software Engineer",
        "Sr. Backend Engineer",
        "Sr Data Engineer",
        "Staff Engineer, Payments",
        "Staff Software Engineer",
        "Principal Engineer",
        "Principal Product Designer",
        "Director of Engineering",
        "VP, Engineering",
        "Vice President of Data",
        "Head of Platform",
        "Backend Engineer (SENIOR)",
    ],
)
def test_explicit_seniority_words_in_the_title_are_rejected(title):
    decision = run_title(title)
    assert decision.verdict is Verdict.REJECT
    reason = next(r for r in decision.reasons if r.code == "SENIORITY_IN_TITLE")
    assert reason.verdict is Verdict.REJECT
    assert reason.evidence == title


@pytest.mark.parametrize(
    "title",
    [
        "Software Engineer, Lead Platform",
        "Tech Lead",
        "Solutions Architect",
        "Engineering Manager",
        "Lead Generation Intern",
        "Architect Intern",
        "Product Manager Intern",
    ],
)
def test_ambiguous_seniority_words_only_need_a_check(title):
    decision = run_title(title)
    assert decision.verdict is Verdict.CHECK
    reason = next(r for r in decision.reasons if r.code == "SENIORITY_IN_TITLE")
    assert reason.verdict is Verdict.CHECK
    assert reason.evidence == title


@pytest.mark.parametrize(
    "title",
    [
        "Software Engineering Intern",
        "New Grad Software Engineer",
        "Junior Backend Engineer",
        "Software Engineer I",
        "Machine Learning Engineer",
        "Staff Accountant",
        "Customer Support Staff",
        "Seniority Calibration Analyst",
        "Seniors Care Coordinator",
        "Leadership Development Program, Graduate",
        "Directorate Liaison Engineer",
        "Principality Data Engineer",
        "Headstart Engineer",
    ],
)
def test_other_titles_are_not_affected_and_words_need_word_boundaries(title):
    assert "SENIORITY_IN_TITLE" not in codes(run_title(title))


def test_seniority_reject_is_reported_once_even_with_ambiguous_words_too():
    decision = run_title("Senior Partner Solutions Architect")
    found = [r for r in decision.reasons if r.code == "SENIORITY_IN_TITLE"]
    assert len(found) == 1 and found[0].verdict is Verdict.REJECT


def test_seniority_looks_at_the_title_only_not_the_description():
    decision = run_title("Software Engineer", "You will work with senior staff and a tech lead.")
    assert "SENIORITY_IN_TITLE" not in codes(decision)


# -- student status (profile.student_status) ---------------------------------------------


def grad_profile(**extra):
    return make_profile(student_status="graduated", **extra)


def run_text(text, profile, title="Software Engineer"):
    return evaluate(make_job(text, title=title), profile)


@pytest.mark.parametrize(
    "text",
    [
        "You are currently enrolled in a Bachelor's or Master's program.",
        "Candidates must be currently pursuing a degree in computer science.",
        "Currently pursuing a BS, MS or PhD in a technical field.",
        "You must be a student at an accredited university.",
        "Applicants must be a current undergraduate student.",
        "You will be returning to school after the internship.",
        "Must be returning to university in the fall.",
        "You are enrolled in a degree program at a university.",
        "Enrolled in an accredited university or college program.",
        "Pursuing a Bachelor's degree in Computer Science.",
    ],
)
def test_current_enrollment_requirements_reject_a_graduated_profile(text):
    decision = run_text(text, grad_profile())
    assert decision.verdict is Verdict.REJECT
    reason = next(r for r in decision.reasons if r.code == "STUDENT_STATUS_REQUIRED")
    assert reason.verdict is Verdict.REJECT
    assert reason.evidence == text


@pytest.mark.parametrize(
    "text",
    [
        "You are currently enrolled in a Bachelor's or Master's program.",
        "Currently pursuing a BS, MS or PhD in a technical field.",
        "You must be a student at an accredited university.",
    ],
)
def test_enrollment_requirement_does_not_affect_other_profiles(text):
    for profile in (make_profile(), make_profile(student_status="enrolled")):
        assert "STUDENT_STATUS_REQUIRED" not in codes(run_text(text, profile))


@pytest.mark.parametrize(
    "text",
    [
        "We mentor students and run a campus ambassador programme.",
        "Our team has supported student loan refinancing for customers.",
        "We partner with student organisations across Europe.",
        "Graduate Software Engineer: join our two-year rotation.",
        "Recent graduates are welcome to apply.",
        "We hire graduates every year and train them on the job.",
        "Employees enrolled in our health plan get free dental care.",
        "Enrolled in the 401k program from day one.",
        "We support employees pursuing a degree with tuition reimbursement.",
        "You will work with students who are returning to school as users of our product.",
        "Students or recent graduates are encouraged to apply.",
        "Open to currently enrolled students or recent graduates.",
        "Pursuing or received a degree in Engineering, Mathematics or Physics.",
        "Currently pursuing or recently completed a Bachelor's or Master's in Computer Science.",
        "Pursuing a degree in Computer Science, or have equivalent practical experience.",
        "Pursuing or having completed a degree in a related field.",
    ],
)
def test_sentences_that_are_not_an_enrollment_requirement_are_not_flagged(text):
    decision = run_text(text, grad_profile())
    assert "STUDENT_STATUS_REQUIRED" not in codes(decision)
    assert decision.verdict is Verdict.PASS


def test_enrollment_requirement_next_to_a_graduates_welcome_sentence_is_only_a_check():
    text = "You are currently pursuing a degree. Recent graduates are welcome too."
    decision = run_text(text, grad_profile())
    assert decision.verdict is Verdict.CHECK
    assert codes(decision) == {"GRADUATION_AMBIGUOUS"}


def test_soft_enrollment_wording_is_only_a_check():
    decision = run_text("Currently pursuing a degree is preferred.", grad_profile())
    assert decision.verdict is Verdict.CHECK
    assert codes(decision) == {"GRADUATION_AMBIGUOUS"}


# -- graduation year (profile.graduation_year) -------------------------------------------


def year_profile(year=2026, **extra):
    return make_profile(graduation_year=year, **extra)


@pytest.mark.parametrize(
    "text",
    [
        "Candidates graduating in 2027.",
        "You are graduating in December 2027.",
        "Open to the class of 2027.",
        "For graduates of 2027 only.",
        "Expected graduation date: June 2027.",
        "You will graduate between 2027 and 2028.",
        "Graduating between December 2027 and June 2028.",
        "Students graduating 2027 - 2028 are eligible.",
        "You are graduating by 2025.",
        "You will have graduated before 2026.",
        "Graduating in 2027 or later.",
        "Graduating in 2025 or earlier.",
        "Graduating in 2027 or 2028.",
        "Graduating after 2026.",
    ],
)
def test_graduation_year_outside_the_profile_year_is_rejected(text):
    decision = run_text(text, year_profile())
    assert decision.verdict is Verdict.REJECT
    reason = next(r for r in decision.reasons if r.code == "GRADUATION_YEAR_MISMATCH")
    assert reason.verdict is Verdict.REJECT
    assert reason.evidence == text


@pytest.mark.parametrize(
    "text",
    [
        "Candidates graduating in 2026.",
        "Open to the class of 2026.",
        "For graduates of 2026.",
        "Graduating between 2025 and 2027.",
        "Graduating between December 2025 and June 2027.",
        "Graduating 2026 - 2027.",
        "Graduating in 2026 or 2027.",
        "Graduating by 2027.",
        "Graduating no later than 2026.",
        "You will graduate before 2027.",
        "Graduating in 2026 or later.",
        "Graduating in 2027 or earlier.",
        "Graduating after 2025.",
    ],
)
def test_graduation_year_that_covers_the_profile_year_is_not_flagged(text):
    decision = run_text(text, year_profile())
    assert decision.verdict is Verdict.PASS
    assert decision.reasons == []


@pytest.mark.parametrize(
    "text",
    [
        "Graduate Software Engineer",
        "Join our graduate programme and grow with us.",
        "Our graduate programme has run since 2019.",
        "We were founded in 2015 and hire graduates every year.",
        "Recent graduates welcome.",
        "You graduated within the last 12 months.",
        "Graduating soon? Apply now.",
        "We have a class of interns each summer and ship in 2027.",
        "Summer 2027 internship in our Berlin office.",
        "Join us in 2027 as we grow.",
    ],
)
def test_text_without_a_graduation_year_requirement_is_not_flagged(text):
    decision = run_text(text, year_profile())
    assert decision.verdict is Verdict.PASS
    assert decision.reasons == []


def test_year_rule_needs_a_graduation_year_in_the_profile():
    text = "Candidates graduating in 2027."
    for profile in (make_profile(), make_profile(student_status="graduated")):
        assert "GRADUATION_YEAR_MISMATCH" not in codes(run_text(text, profile))


def test_year_rule_also_applies_to_an_enrolled_profile():
    profile = make_profile(graduation_year=2028, student_status="enrolled")
    assert run_text("Graduating in 2027.", profile).verdict is Verdict.REJECT
    assert run_text("Graduating in 2028.", profile).verdict is Verdict.PASS


def test_graduation_year_in_the_title_counts_too():
    decision = run_text("", year_profile(), title="Software Engineer (Class of 2027)")
    assert codes(decision) == {"GRADUATION_YEAR_MISMATCH"}
    assert decision.reasons[0].evidence == "Software Engineer (Class of 2027)"


def test_conflicting_year_sentences_are_only_a_check():
    text = "Open to graduates of 2026. Candidates graduating in 2027 are preferred."
    decision = run_text(text, year_profile())
    assert decision.verdict is Verdict.CHECK
    assert codes(decision) == {"GRADUATION_AMBIGUOUS"}


def test_year_requirement_mixed_with_a_recent_graduates_wording_is_only_a_check():
    decision = run_text("Students graduating in 2027 or recent graduates.", year_profile())
    assert decision.verdict is Verdict.CHECK
    assert codes(decision) == {"GRADUATION_AMBIGUOUS"}


def test_soft_year_wording_is_only_a_check():
    decision = run_text("Graduating in 2027 is a plus.", year_profile())
    assert decision.verdict is Verdict.CHECK
    assert codes(decision) == {"GRADUATION_AMBIGUOUS"}


def test_both_education_rules_can_fire_on_one_posting():
    text = "You are currently enrolled in a degree program. Graduating in 2027."
    decision = run_text(text, grad_profile(graduation_year=2026))
    assert decision.verdict is Verdict.REJECT
    assert codes(decision) == {"STUDENT_STATUS_REQUIRED", "GRADUATION_YEAR_MISMATCH"}


def test_profiles_without_education_fields_keep_every_verdict():
    text = "You are currently enrolled in a degree program. Graduating in 2027."
    decision = run_text(text, make_profile())
    assert decision.verdict is Verdict.PASS
