import csv
from pathlib import Path

import pytest

from jobgate.evaluation import (
    FIELDS,
    LabeledPosting,
    build_report,
    evaluate_rows,
    load_labeled,
)
from jobgate.profile import load_profile

REPO_ROOT = Path(__file__).parent.parent
DATA = REPO_ROOT / "tests" / "data" / "labeled_postings.csv"


def row(label, excerpt, location="Berlin, Germany", verified=False, n=1):
    return LabeledPosting(
        id=f"T{n}",
        source="synthetic",
        company="Example Co",
        ats="synthetic",
        title="Engineer",
        location=location,
        source_url="synthetic",
        excerpt=excerpt,
        suggested_label=label,
        suggested_reason="",
        human_verified=verified,
    )


@pytest.fixture(scope="module")
def profile():
    return load_profile(REPO_ROOT / "profile.example.yaml")


def test_metrics_on_a_tiny_set(profile):
    rows = [
        row("blocked", "5+ years of experience required.", n=1),  # rejected: correct
        row("clear", "Build APIs with Python.", n=2),  # passed: correct
        row("uncertain", "Build APIs.", location="Remote", n=3),  # check: correct
        row("clear", "5+ years of experience required.", n=4),  # rejected: false rejection
        row("blocked", "Build APIs with Python.", n=5),  # passed: missed block
    ]
    result = evaluate_rows(rows, profile)
    assert result.total == 5
    assert result.correct == 3
    assert result.accuracy == pytest.approx(0.6)
    assert result.false_rejections == 1
    assert result.non_blocked == 3
    assert result.false_rejection_rate == pytest.approx(1 / 3)
    assert result.missed_blocks == 1
    assert result.blocked == 2
    assert result.missed_block_rate == pytest.approx(0.5)
    assert [m.posting.id for m in result.mismatches] == ["T4", "T5"]


def test_empty_set_has_no_rates(profile):
    result = evaluate_rows([], profile)
    assert result.total == 0
    assert result.accuracy is None
    assert result.false_rejection_rate is None


def test_report_never_claims_the_target_without_verified_rows(profile):
    report = build_report([row("clear", "Build APIs.")], profile)
    assert "Human-verified rows: 0" in report
    assert "not measurable" in report.lower()
    assert "target met" not in report.lower()


def test_report_shows_both_numbers_for_verified_rows(profile):
    rows = [row("clear", "Build APIs.", verified=True, n=i) for i in range(10)]
    report = build_report(rows, profile)
    assert "Accuracy: 100.0%" in report
    assert "False rejection rate: 0.0%" in report
    assert "target met" in report.lower()


def test_report_fails_the_target_below_ninety_percent(profile):
    rows = [row("clear", "Build APIs.", verified=True, n=i) for i in range(8)]
    rows += [row("clear", "5+ years of experience.", verified=True, n=i + 20) for i in range(2)]
    report = build_report(rows, profile)
    assert "Accuracy: 80.0%" in report
    assert "target not met" in report.lower()


def test_load_labeled_reads_booleans_and_rejects_bad_labels(tmp_path):
    path = tmp_path / "set.csv"
    base = dict.fromkeys(FIELDS, "x")
    good = {**base, "suggested_label": "clear", "human_verified": "TRUE"}
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerow(good)
    assert load_labeled(path)[0].human_verified is True
    bad = {**good, "suggested_label": "maybe"}
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerow(bad)
    with pytest.raises(ValueError, match="maybe"):
        load_labeled(path)


# -- the committed labelled set ----------------------------------------------------------


def test_committed_set_has_forty_postings_with_all_three_labels():
    rows = load_labeled(DATA)
    assert len(rows) == 40
    assert {r.suggested_label for r in rows} == {"blocked", "clear", "uncertain"}
    assert len({r.id for r in rows}) == 40


def test_committed_set_stores_short_quotes_with_a_source_not_full_postings():
    for r in load_labeled(DATA):
        assert len(r.excerpt) <= 400, r.id
        assert r.source in {"real", "synthetic"}
        assert r.source_url.startswith("https://") or r.source == "synthetic"


def test_committed_set_contains_no_personal_data():
    text = DATA.read_text(encoding="utf-8").lower()
    assert "@" not in text  # no e-mail addresses


def test_filter_accuracy_on_the_committed_set(profile):
    rows = load_labeled(DATA)
    # Preliminary: uses suggested (unverified) labels, so it is a regression guard only.
    assert evaluate_rows(rows, profile).accuracy >= 0.90
    verified = [r for r in rows if r.human_verified]
    if verified:  # the real target, enforced as soon as the owner verifies rows
        result = evaluate_rows(verified, profile)
        assert result.accuracy >= 0.90


def test_correct_decisions_carry_the_expected_reason_code(profile):
    for outcome in evaluate_rows(load_labeled(DATA), profile).outcomes:
        expected = outcome.posting.suggested_reason
        if expected and outcome.correct:
            assert expected in outcome.decision.codes, outcome.posting.id


# -- the held-out batch (filter was never tuned on it) -----------------------------------

HELDOUT = REPO_ROOT / "tests" / "data" / "heldout_postings.csv"


def test_heldout_batch_has_at_least_25_unverified_real_postings():
    rows = load_labeled(HELDOUT)
    assert len(rows) >= 25
    assert all(r.source == "real" and r.source_url.startswith("https://") for r in rows)
    assert not any(r.human_verified for r in rows)
    assert all(len(r.excerpt) <= 400 for r in rows)


def test_heldout_batch_does_not_overlap_the_development_set():
    dev_urls = {r.source_url for r in load_labeled(DATA)}
    assert not dev_urls & {r.source_url for r in load_labeled(HELDOUT)}


def test_heldout_report_does_not_claim_the_filter_was_tuned_on_it(profile):
    rows = [row("clear", "Build APIs.")]
    assert "was tuned" in build_report(rows, profile)
    heldout = build_report(rows, profile, heldout=True)
    assert "was tuned" not in heldout
    assert "not tuned" in heldout.lower()
