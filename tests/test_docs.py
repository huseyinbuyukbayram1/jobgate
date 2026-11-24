"""Guards for the public docs: the pending-gate rules and the promises the README makes."""

import re
from pathlib import Path

import pytest

from jobgate.profile import load_profile

ROOT = Path(__file__).parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
CHANGELOG = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["README.md", "CHANGELOG.md"])
def test_no_accuracy_number_while_labels_are_unverified(name):
    text = (ROOT / name).read_text(encoding="utf-8")
    for line in text.splitlines():
        if re.search(r"accura|false[- ]reject|missed[- ]block", line, re.I):
            assert not re.search(r"\d+(?:\.\d+)?\s*%|\b\d+\s*/\s*\d+\b", line), line


def test_readme_discloses_ai_assisted_development():
    assert "Claude Code" in README and "AI assistance" in README


def test_readme_marks_unverified_terms_links_instead_of_inventing_them():
    assert README.count("to be verified") >= 3


def test_readme_says_what_it_does_not_do_and_has_the_diagram():
    assert "does not apply for you" in README
    assert "```mermaid" in README


def test_readme_profile_snippet_is_a_valid_profile(tmp_path):
    snippet = re.search(r"```yaml\n(work_authorization.*?)```", README, re.S).group(1)
    path = tmp_path / "profile.yaml"
    path.write_text(snippet, encoding="utf-8")
    assert load_profile(path).max_experience_years == 2


def test_every_command_the_readme_shows_exists():
    from typer.testing import CliRunner

    from jobgate import cli

    commands = set(re.findall(r"^\s*jobgate (\w+)", README, re.M))
    help_text = CliRunner().invoke(cli.app, ["--help"], env={"COLUMNS": "200"}).output
    for command in commands:
        assert command in help_text, command


def test_readme_evaluation_section_matches_the_label_files():
    import csv

    assert "## Evaluation" in README and "makes no accuracy claim" in README
    for name in ("labeled_postings.csv", "heldout_postings.csv"):
        with (ROOT / "tests" / "data" / name).open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        verified = sum(r["human_verified"].strip().lower() == "true" for r in rows)
        assert f"{verified} / {len(rows)}" in README, name
