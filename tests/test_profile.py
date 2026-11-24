from pathlib import Path

import pytest

from jobgate.profile import Profile, ProfileError, load_profile

REPO_ROOT = Path(__file__).parent.parent


def write(tmp_path, text):
    path = tmp_path / "profile.yaml"
    path.write_text(text, encoding="utf-8")
    return path


MINIMAL = """
work_authorization: {regions: [Germany]}
locations: {allowed: [Germany]}
"""


def test_example_profile_is_valid_and_fictional():
    profile = load_profile(REPO_ROOT / "profile.example.yaml")
    assert profile.max_experience_years == 2
    assert "english" in profile.languages
    text = (REPO_ROOT / "profile.example.yaml").read_text(encoding="utf-8").lower()
    assert "fictional" in text
    assert "@" not in text  # no e-mail address of any kind


def test_minimal_profile_gets_safe_defaults(tmp_path):
    profile = load_profile(write(tmp_path, MINIMAL))
    assert profile.security_clearance is False
    assert profile.blockers.video_requirement == "reject"
    assert profile.blockers.take_home_assignment == "reject"
    assert profile.languages == ["english"]


def test_values_are_lowercased_for_matching(tmp_path):
    profile = load_profile(write(tmp_path, MINIMAL + "languages: [English, DEUTSCH]\n"))
    assert profile.languages == ["english", "deutsch"]
    assert profile.locations.allowed == ["germany"]


def test_negative_experience_is_rejected(tmp_path):
    with pytest.raises(ProfileError, match="max_experience_years"):
        load_profile(write(tmp_path, MINIMAL + "max_experience_years: -1\n"))


def test_unknown_key_is_rejected(tmp_path):
    with pytest.raises(ProfileError, match="nickname"):
        load_profile(write(tmp_path, MINIMAL + "nickname: x\n"))


def test_bad_blocker_mode_is_rejected(tmp_path):
    with pytest.raises(ProfileError, match="video_requirement"):
        load_profile(write(tmp_path, MINIMAL + "blockers: {video_requirement: maybe}\n"))


def test_missing_and_broken_files_give_profile_errors(tmp_path):
    with pytest.raises(ProfileError, match="not found"):
        load_profile(tmp_path / "nope.yaml")
    with pytest.raises(ProfileError, match="YAML"):
        load_profile(write(tmp_path, "locations: [unclosed"))


def test_profile_can_be_built_in_code():
    profile = Profile.model_validate(
        {"work_authorization": {"regions": ["x"]}, "locations": {"allowed": ["x"]}}
    )
    assert profile.max_experience_years == 2
