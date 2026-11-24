"""Measure the blocker filter against a labelled set of postings.

The labelled set is a CSV of short excerpts. Labels start as *suggestions*; only rows
whose ``human_verified`` column was set to true by the owner count toward the real
accuracy target. Numbers on unverified rows are reported separately as preliminary.

Run: ``python -m jobgate.evaluation --out docs/filter_report.md``
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from jobgate.filters import Decision, Verdict, evaluate
from jobgate.models import Job
from jobgate.profile import Profile, load_profile

FIELDS = [
    "id", "source", "company", "ats", "title", "location", "source_url",
    "excerpt", "suggested_label", "suggested_reason", "human_verified",
]  # fmt: skip
LABEL_TO_VERDICT = {
    "blocked": Verdict.REJECT,
    "clear": Verdict.PASS,
    "uncertain": Verdict.CHECK,
}
TARGET_ACCURACY = 0.90


@dataclass(frozen=True)
class LabeledPosting:
    id: str
    source: str
    company: str
    ats: str
    title: str
    location: str
    source_url: str
    excerpt: str
    suggested_label: str
    suggested_reason: str
    human_verified: bool

    @property
    def expected(self) -> Verdict:
        return LABEL_TO_VERDICT[self.suggested_label]

    def to_job(self) -> Job:
        return Job(
            company=self.company or "unknown",
            title=self.title or "unknown",
            location=self.location,
            description=self.excerpt,
            url=self.source_url if self.source_url.startswith("http") else "https://example.com",
            ats="greenhouse" if self.ats == "synthetic" else self.ats,  # type: ignore[arg-type]
            ats_job_id=self.id,
        )


@dataclass(frozen=True)
class Outcome:
    posting: LabeledPosting
    decision: Decision

    @property
    def correct(self) -> bool:
        return self.decision.verdict is self.posting.expected


@dataclass
class EvalResult:
    outcomes: list[Outcome] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.outcomes)

    @property
    def correct(self) -> int:
        return sum(o.correct for o in self.outcomes)

    @property
    def accuracy(self) -> float | None:
        return self.correct / self.total if self.total else None

    @property
    def blocked(self) -> int:
        return sum(o.posting.suggested_label == "blocked" for o in self.outcomes)

    @property
    def non_blocked(self) -> int:
        return self.total - self.blocked

    @property
    def false_rejections(self) -> int:
        """Postings that are NOT blocked but the filter rejected anyway (the costly error)."""
        return sum(
            o.posting.suggested_label != "blocked" and o.decision.verdict is Verdict.REJECT
            for o in self.outcomes
        )

    @property
    def false_rejection_rate(self) -> float | None:
        return self.false_rejections / self.non_blocked if self.non_blocked else None

    @property
    def missed_blocks(self) -> int:
        """Blocked postings the filter let through without even a 'check'."""
        return sum(
            o.posting.suggested_label == "blocked" and o.decision.verdict is Verdict.PASS
            for o in self.outcomes
        )

    @property
    def missed_block_rate(self) -> float | None:
        return self.missed_blocks / self.blocked if self.blocked else None

    @property
    def mismatches(self) -> list[Outcome]:
        return [o for o in self.outcomes if not o.correct]

    def confusion(self) -> Counter[tuple[str, str]]:
        return Counter((o.posting.suggested_label, o.decision.verdict.value) for o in self.outcomes)


def load_labeled(path: Path | str) -> list[LabeledPosting]:
    rows: list[LabeledPosting] = []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            label = raw["suggested_label"].strip().lower()
            if label not in LABEL_TO_VERDICT:
                raise ValueError(f"row {raw.get('id')}: unknown label {label!r}")
            rows.append(
                LabeledPosting(
                    **{k: raw[k] for k in FIELDS if k not in ("suggested_label", "human_verified")},
                    suggested_label=label,
                    human_verified=raw["human_verified"].strip().lower() == "true",
                )
            )
    return rows


def evaluate_rows(rows: list[LabeledPosting], profile: Profile) -> EvalResult:
    return EvalResult([Outcome(r, evaluate(r.to_job(), profile)) for r in rows])


# -- report -----------------------------------------------------------------------------


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _metrics(result: EvalResult) -> list[str]:
    return [
        f"- Accuracy: {_pct(result.accuracy)} ({result.correct}/{result.total})",
        f"- False rejection rate: {_pct(result.false_rejection_rate)} "
        f"({result.false_rejections} of {result.non_blocked} non-blocked postings were rejected)",
        f"- Missed-block rate: {_pct(result.missed_block_rate)} "
        f"({result.missed_blocks} of {result.blocked} blocked postings passed unflagged)",
    ]


def build_report(rows: list[LabeledPosting], profile: Profile, heldout: bool = False) -> str:
    everything = evaluate_rows(rows, profile)
    verified = evaluate_rows([r for r in rows if r.human_verified], profile)
    lines = [
        "# Filter accuracy report",
        "",
        "Generated by `python -m jobgate.evaluation`. Profile: `profile.example.yaml` "
        "(a fictional person). Labels: blocked = must be rejected, clear = must pass, "
        "uncertain = must be flagged for a check.",
        "",
        "## Human-verified rows (the real target)",
        "",
        f"Human-verified rows: {verified.total} of {everything.total}",
        "",
    ]
    if verified.total == 0:
        lines += [
            "Accuracy and false rejection rate are not measurable yet: no row has been "
            "verified by the owner. See `docs/labeling.md`.",
        ]
    else:
        lines += _metrics(verified)
        met = (verified.accuracy or 0) >= TARGET_ACCURACY
        lines += [
            f"- Target (accuracy >= {TARGET_ACCURACY:.0%}): "
            + ("target met" if met else "target not met"),
        ]
    lines += [
        "",
        "## Preliminary: all rows, using suggested (unverified) labels",
        "",
        (
            "These labels were proposed by the AI assistant. The filter was not tuned on "
            "these rows (held-out batch), but the labels are still unverified."
            if heldout
            else "These labels were proposed by the AI assistant and the filter was tuned while "
            "looking at many of these rows, so treat the numbers as optimistic."
        ),
        "",
        *_metrics(everything),
        "",
        "## Confusion matrix (preliminary)",
        "",
        "| label \\ verdict | pass | check | reject |",
        "|---|---|---|---|",
    ]
    confusion = everything.confusion()
    for label in LABEL_TO_VERDICT:
        cells = " | ".join(str(confusion[(label, v)]) for v in ("pass", "check", "reject"))
        lines.append(f"| {label} | {cells} |")
    lines += ["", "## Mismatches (preliminary)", ""]
    if not everything.mismatches:
        lines.append("None.")
    else:
        lines += ["| id | label | verdict | reason codes | excerpt |", "|---|---|---|---|---|"]
        for o in everything.mismatches:
            excerpt = o.posting.excerpt.replace("|", "/")[:120]
            codes = ", ".join(o.decision.codes) or "-"
            lines.append(
                f"| {o.posting.id} | {o.posting.suggested_label} | "
                f"{o.decision.verdict.value} | {codes} | {excerpt} |"
            )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure the blocker filter on the labelled set.")
    parser.add_argument("--set", default="tests/data/labeled_postings.csv", help="labelled CSV")
    parser.add_argument("--profile", default="profile.example.yaml", help="profile YAML")
    parser.add_argument("--out", help="write the Markdown report here instead of stdout")
    parser.add_argument(
        "--heldout", action="store_true", help="the set was never used to tune the filter"
    )
    args = parser.parse_args(argv)
    report = build_report(load_labeled(args.set), load_profile(args.profile), args.heldout)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
