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
    section = README.split("## How this project is built", 1)[1].split("\n## ", 1)[0]
    assert "Claude Code" in section and "AI coding" in section
    assert "suggested by the AI assistant" in section and "not yet" in section
    assert "labelling are done by the repository owner" not in README


def test_readme_limitations_and_roadmap_cover_graduation_year_and_wording():
    assert "hand-collected" not in README and "collected by the tooling" in README
    assert README.count("docs/issue_drafts/graduation-year-rule.md") >= 2
    assert (ROOT / "docs" / "issue_drafts" / "graduation-year-rule.md").exists()
    assert "Windows" in README and "Activate.ps1" in README
    assert README.index("Who it's for") < README.index("jobgate is an open-source")


def test_readme_lists_the_documented_links_and_the_customer_terms_note():
    for link in (
        "https://developers.greenhouse.io/job-board.html",
        "https://github.com/lever/postings-api",
        "https://www.lever.co/terms-of-service",
        "https://developers.ashbyhq.com/docs/public-job-posting-api",
        "https://www.ashbyhq.com/terms",
    ):
        assert link in README, link
    note = "customer terms; no separate terms for the public job-board API were found"
    assert README.count(note) == 2
    assert "to be verified" not in README


def test_readme_has_a_responsible_use_section_with_a_legal_disclaimer():
    section = README.split("## Responsible use", 1)[1].split("\n## ", 1)[0]
    for phrase in ("User-Agent", "cached", "switched off", "not legal advice"):
        assert phrase in section, phrase


def test_sources_doc_carries_the_same_terms_information():
    sources = (ROOT / "docs" / "sources.md").read_text(encoding="utf-8")
    assert "https://www.lever.co/terms-of-service" in sources
    assert "https://www.ashbyhq.com/terms" in sources
    assert "not legal advice" in sources


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


def test_docs_folder_has_no_accuracy_percentages():
    for path in sorted((ROOT / "docs").rglob("*.md")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if re.search(r"accura|false[- ]reject|missed[- ]block|wrongly rejected", line, re.I):
                assert "%" not in line, f"{path.name}: {line}"
