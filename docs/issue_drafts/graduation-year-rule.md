# Issue draft: student / graduation-year rule

**Status:** implemented in `[Unreleased]` in a reduced form (see `CHANGELOG.md`). What was built
differs from the draft below: the profile has two flat optional fields, `student_status`
(`graduated` | `enrolled`) and `graduation_year`, not an `education:` block; there is no month
field; the reject code for a wrong year is `GRADUATION_YEAR_MISMATCH`; ambiguous or conflicting
wording uses `GRADUATION_AMBIGUOUS` (check). Not built: `GRADUATION_WINDOW_UNCLEAR` ("within N
months of graduation"), month-level ranges, and season wording ("Summer 2027") implying a year.
The text below is the original draft, kept for the reasoning.

## Problem

Many new-grad and internship postings restrict who may apply by study status, not by years of
experience: "currently enrolled", "must graduate in 2027", "graduating between December 2026 and
June 2027", "recent graduates only (within 12 months)". The experience-years rule does not see
these, so a posting can pass although the user is not eligible (or be rejected although they are).

## Proposed profile fields (`profile.yaml`)

```yaml
education:
  status: graduated            # student | graduated
  graduation_year: 2026        # year the degree was or will be completed
  graduation_month: 6          # optional, 1-12
```

All optional. If `education` is missing the rule does nothing, so existing profiles keep working.

## Proposed rule (`filters.py`)

Sentence-level, like the other rules, and it prefers **check** over a wrong **reject**.

| Posting says | Profile | Verdict | Reason code |
|--------------|---------|---------|-------------|
| "currently enrolled / pursuing a degree / must be a student" | `status: graduated` | reject | `STUDENT_STATUS_REQUIRED` |
| "graduating in 2027" (a year or range) | `graduation_year` outside it | reject | `GRADUATION_YEAR_OUTSIDE` |
| "within N months of graduation" / "recent graduate" with a number | date outside the window | check | `GRADUATION_WINDOW_UNCLEAR` |
| enrolled-or-recent-graduate wording ("students or recent graduates") | any | pass | none |
| year or status stated ambiguously or in conflicting sentences | any | check | `GRADUATION_AMBIGUOUS` |

Details to settle in the issue: month-level ranges ("December 2026 - June 2027"); the season
wording ("Summer 2027 intern") which implies a year; ignoring text such as "graduated 5 years ago".

## Tests (written before the code)

- One passing and one rejecting example per row of the table, with short synthetic sentences.
- A profile without `education` leaves every existing verdict unchanged (run both labelled sets
  before and after and compare).
- Add a few real, quoted postings to the held-out set as `uncertain` or `blocked` rows with
  `human_verified=false`.

## Out of scope

Reading dates from a CV, guessing a graduation year, any LLM involvement.
