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

The report prints rates only for verified rows, and only once at least 20 rows are verified; until then it prints counts. The accuracy target is in `PROJECT_LOG.md`. The false rejection rate (postings
that are not blocked but were rejected) is reported separately because wrongly dropping a
good posting is the costly mistake.

## Known limits of this set

- 40 rows is small; one wrong row moves accuracy by 2.5 points.
- The filter was tuned while looking at many of these rows, so numbers on them are
  optimistic. A fresh, unseen batch labelled by the owner is the honest test.
- Real excerpts come from 30 well-known companies fetched on 2026-11-24 and skew toward
  sales and customer-facing roles, where language and location rules appear most often.

## Held-out batch

`tests/data/heldout_postings.csv` is a second set of 28 real junior and new-grad software,
AI and data engineering postings from 23 companies that were **not** used to build the first
set. Its labels were written down and committed **before the filter was ever run on it**, and
the filter must not be changed to fit it (a later fix would turn it into a second development
set). Same columns and same verification steps as above.

Known limits of this batch:

- It has no `uncertain` rows. Real junior postings almost never contain wording that is
  truly ambiguous, so the "check" class is only covered by the first set.
- Many rows are blocked by location alone (most new-grad postings are in the US). That is
  realistic for the example profile but it means the batch tests location more than the
  other rules.
- Two rows (Cloudflare, location field `In-Office`) put the real city only in the text, which
  the filter does not read for location. Their labels follow what a human would conclude.

### What the first run on the held-out batch showed (recorded, not fixed)

The filter was run on this batch once, after the labels were committed, and then left alone.
Result in `docs/heldout_report.md` (preliminary, unverified labels). Findings:

1. Both mismatches are the Cloudflare `In-Office` rows: the filter says "check" because the
   location field is unclear, while the real city is only in the text. Safe direction.
2. One row was rejected for the wrong reason: Palantir's "A 3-minute response to our
   application video prompt." is a video requirement the video rule does not recognise; the
   row was rejected only because of its location (Seoul). A video-only posting in an allowed
   location would slip through.

These are candidates for a later fix, to be checked on a *new* unseen batch.
