# Labelled posting set

`tests/data/labeled_postings.csv` holds 40 short excerpts used to measure the blocker
filter. It stores **only** the sentences that matter for a rule, each with a link to the
source posting (or `synthetic` when I wrote the sentence myself). No full posting text is
stored.

Labels are judged against `profile.example.yaml` (a fictional new graduate in Germany
with EU work rights, English and German, at most 2 years of experience asked).

| label | meaning | filter must return |
|-------|---------|--------------------|
| `blocked` | a hard blocker for this profile | `reject` |
| `clear` | nothing in the excerpt blocks this profile | `pass` |
| `uncertain` | unclear or contradicting wording, a human should look | `check` |

## How the owner verifies labels

The labels were **suggested by the AI assistant** by reading the excerpts. They do not count
toward the accuracy target until a human confirms them:

1. Open the CSV and read each row (follow `source_url` for real rows).
2. If you disagree, change `suggested_label`.
3. Set `human_verified` to `true` for every row you checked.
4. Run `python -m jobgate.evaluation --out docs/filter_report.md` and commit the report.

The target is at least 90% accuracy on verified rows. The false rejection rate (postings
that are not blocked but were rejected) is reported separately because wrongly dropping a
good posting is the costly mistake.

## Known limits of this set

- 40 rows is small; one wrong row moves accuracy by 2.5 points.
- The filter was tuned while looking at many of these rows, so numbers on them are
  optimistic. A fresh, unseen batch labelled by the owner is the honest test.
- Real excerpts come from 30 well-known companies fetched on 2026-11-24 and skew toward
  sales and customer-facing roles, where language and location rules appear most often.
