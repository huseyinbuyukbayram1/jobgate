# Issue draft: senior roles can rank high on technology words alone

**Status:** draft only, nothing implemented.

## Problem

The score adds five parts. The level part (`scoring.py`, `_level_ratio`) gives **0 points** when
the title contains a seniority word (senior, sr, staff, principal, lead, manager, director,
head of, vp, architect). That is all it does: nothing is subtracted from the other parts, and the
posting is not flagged. A senior posting that matches many of the profile's technologies and
location therefore keeps those points and can still rank near the top, especially when few
postings in the run score well.

## Example

A real run with `profile.example.yaml` and `companies.example.yaml` (2026-11-24):

```text
40: technology 30, location 10  Senior Partner Solutions Architect (Pan-EMEA GSI) @ Datadog
```

Level is missing from the breakdown (zero points). Technology and location carry the score to
second place, above entry-level postings that matched fewer technology words.

The experience filter did not help here because the posting states no years of experience in
the sentences it reads.

## Possible solutions

1. **Penalty.** When the title has a seniority word (senior, staff, principal, lead), subtract a
   fixed number of points (configurable in `scoring.yaml`) or cap the total, so these postings
   fall below postings with a junior or neutral title.
2. **Send to "check".** Treat a seniority word in the title as a filter reason
   (for example `SENIORITY_IN_TITLE`, verdict `check`), so the posting moves to the "Needs a
   check" section instead of the ranked list. Rejecting outright is riskier: "Lead" and
   "Architect" appear in some junior-friendly titles.
3. **Both:** check for the clear words (senior, staff, principal), penalty only for the weaker
   ones (lead, manager).

## Tests (written before the code)

- One title per seniority word: not ranked above the same posting with a neutral title.
- Junior titles ("Junior", "New Grad", "Engineer I") unchanged.
- Compare both labelled sets before and after: no verdict may change for solution 1, and for
  solution 2 list every row whose verdict changes.

## Out of scope

Reading seniority from the description, or any LLM involvement.
