from pathlib import Path

import pytest

from jobgate.models import Job
from jobgate.profile import Profile, load_profile
from jobgate.scoring import DEFAULT_WEIGHTS, ScoringError, Weights, load_weights, score_job

REPO_ROOT = Path(__file__).parent.parent


def make_profile(**preferences):
    prefs = {
        "target_roles": ["software engineer", "data engineer"],
        "avoid_roles": ["sales"],
        "technologies": ["python", "sql", "docker", "c++"],
        "work_modes": ["remote", "hybrid"],
    }
    prefs.update(preferences)
    return Profile.model_validate(
        {
            "work_authorization": {"regions": ["germany"]},
            "locations": {"allowed": ["germany", "berlin", "europe"]},
            "max_experience_years": 2,
            "preferences": prefs,
        }
    )


def make_job(title="Software Engineer", location="Berlin, Germany", description="", **kw):
    return Job(
        company="Acme",
        title=title,
        location=location,
        description=description,
        url="https://example.com/1",
        ats="greenhouse",
        ats_job_id="1",
        **kw,
    )


def score(job, profile=None, weights=DEFAULT_WEIGHTS):
    return score_job(job, profile or make_profile(), weights)


# -- weights -----------------------------------------------------------------------------


def test_default_weights_match_the_documented_split_and_sum_to_100():
    w = DEFAULT_WEIGHTS
    assert (w.role, w.technology, w.level, w.location, w.compensation) == (30, 30, 20, 10, 10)


def test_weights_must_add_up_to_100():
    with pytest.raises(ValueError, match="100"):
        Weights(role=30, technology=30, level=20, location=10, compensation=20)


def test_example_weights_file_loads_and_equals_the_defaults():
    assert load_weights(REPO_ROOT / "scoring.example.yaml") == DEFAULT_WEIGHTS


def test_load_weights_reports_bad_files(tmp_path):
    bad = tmp_path / "w.yaml"
    bad.write_text("weights: {role: 50, technology: 30, level: 20, location: 10, compensation: 10}")
    with pytest.raises(ScoringError, match="100"):
        load_weights(bad)
    with pytest.raises(ScoringError, match="not found"):
        load_weights(tmp_path / "missing.yaml")


def test_load_weights_without_a_path_gives_defaults():
    assert load_weights(None) == DEFAULT_WEIGHTS


def test_custom_weights_change_the_score():
    heavy_role = Weights(role=60, technology=10, level=10, location=10, compensation=10)
    job = make_job()
    assert score(job, weights=heavy_role).parts["role"] == 60
    assert score(job).parts["role"] == 30


# -- role --------------------------------------------------------------------------------


def test_exact_target_role_gets_full_role_points():
    assert score(make_job(title="Software Engineer, Payments")).parts["role"] == 30


def test_partial_title_match_gets_proportional_points():
    # "backend engineer" vs target "data engineer": 1 of 2 words match
    result = score(make_job(title="Backend Engineer"), make_profile(target_roles=["data engineer"]))
    assert result.parts["role"] == 15


def test_unrelated_title_gets_no_role_points():
    assert score(make_job(title="Office Manager")).parts["role"] == 0


def test_avoided_role_in_title_zeroes_the_role_score():
    assert score(make_job(title="Sales Software Engineer")).parts["role"] == 0


# -- technology --------------------------------------------------------------------------


def test_technology_points_grow_with_matches_and_saturate():
    p = make_profile()
    none = score(make_job(description="We build things."), p).parts["technology"]
    one = score(make_job(description="Python."), p).parts["technology"]
    three = score(make_job(description="Python, SQL and Docker."), p).parts["technology"]
    four = score(make_job(description="Python SQL Docker C++"), p).parts["technology"]
    assert none == 0
    assert 0 < one < three
    assert three == four == 30


def test_technology_matching_uses_whole_words():
    # "sql" must not match inside "mysqlx", "c++" must match literally
    assert score(make_job(description="mysqlx"), make_profile()).parts["technology"] == 0
    assert (
        score(make_job(description="We write C++ daily."), make_profile()).parts["technology"] > 0
    )


def test_technology_saturation_is_configurable():
    w = Weights(technology_saturation=1)
    assert score(make_job(description="Python."), weights=w).parts["technology"] == 30


# -- level -------------------------------------------------------------------------------


def test_junior_title_gets_full_level_points():
    assert score(make_job(title="Junior Software Engineer")).parts["level"] == 20
    assert score(make_job(title="Software Engineer, New Grad")).parts["level"] == 20


def test_senior_title_gets_no_level_points():
    assert score(make_job(title="Senior Software Engineer")).parts["level"] == 0
    assert score(make_job(title="Engineering Manager")).parts["level"] == 0


def test_level_falls_back_to_years_asked():
    low = score(make_job(description="1 year of experience.")).parts["level"]
    at_limit = score(make_job(description="2 years of experience.")).parts["level"]
    unknown = score(make_job(description="Build APIs.")).parts["level"]
    above = score(make_job(description="5+ years of experience.")).parts["level"]
    assert low > at_limit > above
    assert unknown == 10


def test_entry_level_wording_in_text_helps():
    text = "This is an entry-level role for recent graduates."
    assert score(make_job(description=text)).parts["level"] == 18


# -- location / work mode ----------------------------------------------------------------


def test_allowed_location_with_preferred_mode_gets_full_location_points():
    job = make_job(location="Berlin, Germany", workplace_type="Hybrid")
    assert score(job).parts["location"] == 10


def test_unknown_work_mode_and_unclear_location_get_partial_points():
    job = make_job(location="Remote")
    # location unclear -> 0.5, mode inferred "remote" is preferred -> 1.0
    assert score(job).parts["location"] == round(10 * (0.6 * 0.5 + 0.4 * 1.0))


def test_unwanted_work_mode_loses_points():
    job = make_job(location="Berlin, Germany", workplace_type="on-site")
    assert score(job).parts["location"] == 6


def test_location_outside_profile_gets_no_location_points_for_place():
    job = make_job(location="Tokyo, Japan", workplace_type="remote")
    assert score(job).parts["location"] == 4


# -- compensation ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "The base range is $87,069-$120,000 per year.",
        "Salary: EUR 55,000 to 65,000.",
        "Pay range 60k - 80k.",
    ],
)
def test_disclosed_pay_gets_compensation_points(text):
    assert score(make_job(description=text)).parts["compensation"] == 10


def test_no_pay_information_gets_no_compensation_points():
    assert score(make_job(description="Competitive salary.")).parts["compensation"] == 0


# -- totals and explanation --------------------------------------------------------------


def test_total_is_the_sum_of_the_parts_and_within_bounds():
    job = make_job(
        title="Junior Software Engineer",
        description="Python, SQL, Docker. Pay range $60,000-$80,000.",
        workplace_type="hybrid",
    )
    result = score(job)
    assert result.total == sum(result.parts.values()) == 100


def test_explanation_lists_nonzero_parts_in_the_documented_format():
    job = make_job(title="Software Engineer", description="Python and SQL.")
    result = score(job)
    text = result.explain()
    assert text.startswith(f"{result.total}: role 30")
    assert "technology 20" in text
    assert "compensation" not in text  # zero parts are left out


def test_score_of_an_empty_match_is_low_but_valid():
    job = make_job(title="Office Manager", location="Tokyo", description="")
    result = score(job)
    assert 0 <= result.total <= 100


def test_scoring_the_example_profile_works():
    profile = load_profile(REPO_ROOT / "profile.example.yaml")
    result = score_job(
        make_job(title="Machine Learning Engineer", description="PyTorch and Python."),
        profile,
        DEFAULT_WEIGHTS,
    )
    assert result.parts["role"] == 30
