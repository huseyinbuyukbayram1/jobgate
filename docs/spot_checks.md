# Spot check: student-status and graduation-year rejections

- **Date:** 2026-11-25
- **Seed:** 42
- **Rule codes:** `STUDENT_STATUS_REQUIRED`, `GRADUATION_YEAR_MISMATCH`
- **Sample:** 10 decisions per code, 20 in total
- **Run:** one real run with `profile.example.yaml` (a fictional graduate: `student_status: graduated`,
  `graduation_year: 2026`) on the 10 companies of `companies.example.yaml`. That run contained 56
  decisions carrying `STUDENT_STATUS_REQUIRED` and 68 carrying `GRADUATION_YEAR_MISMATCH`.
- **Who judged:** the AI assistant that helps build this project sampled the rows and read and
  judged every one. The repository owner has **not** read these 20 decisions yet.

## How the sample was drawn

For each code, the postings carrying that code were sorted by their internal key and 10 were
drawn with Python's `random.Random(42).sample`. Only postings where the code was the first or the
only reason were eligible, so the sample does not show rejections that another rule had already
decided.

The draw is done by [`scripts/spot_check_sample.py`](../scripts/spot_check_sample.py), which takes
the database, the seed and the number of rows and prints the same Markdown rows every time:

```bash
python scripts/spot_check_sample.py --db jobgate.db --seed 42 --count 10 --out sample.md
```

The script was added after this sample was drawn. Run on the database of the same run (2026-11-25,
before any later fetch) it gives these 20 postings in this order. The database itself is not in
the repository, and a database from another day holds different postings, so a later run draws
different rows with the same seed.

The evidence sentence is shown exactly as the filter stored it (the filter cuts a sentence at
200 characters). The judgement was made on that sentence and the title, not on the full posting.

## What was judged

One question per row: given the profile above, is rejecting this posting on this sentence right?
Every row below was marked **reject correct** by the AI assistant.

## `STUDENT_STATUS_REQUIRED`

| No | Company | Title | Verdict on the reject | Evidence | Posting |
|----|---------|-------|-----------------------|----------|---------|
| 1 | Zoox | Software Engineer Intern, Software Platforms & Product [Summer 2027] | reject correct | Expected to graduate between Fall 2027 and Summer 2028, and enrolled at an accredited college or university throughout the internship | https://jobs.lever.co/zoox/88f6cb68-1534-44af-80db-10e43c203520 |
| 2 | Ramp | Applied Scientist Intern | reject correct | Student: currently pursuing a degree in Data Science, Computer Science, Math, Physics, Economics, Statistics, or other quantitative fields with an expected graduation date between Dec 2027 - 2029. | https://jobs.ashbyhq.com/ramp/b39ceb08-a0a7-4f8b-a760-2fb88e209956 |
| 3 | Notion | Software Engineer Intern, Mobile (Winter 2027) | reject correct | - Pursuing a Bachelor's or Master’s degree in computer science, engineering, or another related field. | https://jobs.ashbyhq.com/notion/2b587e66-deac-421a-a824-9415ba78b5a7 |
| 4 | Datadog | Research Science Intern (PhD) | reject correct | Currently enrolled in a PhD program at Carnegie Mellon in machine learning, computer science, statistics, or a related field | https://careers.datadoghq.com/detail/8203657/?gh_jid=8203657 |
| 5 | Cloudflare | People Team Intern, HR Transformation (Winter 2027) | reject correct | Currently enrolled in a program studying business or similar. | https://boards.greenhouse.io/cloudflare/jobs/8350166?gh_jid=8350166 |
| 6 | Cloudflare | Software Engineer Intern (2027) - London, UK | reject correct | Currently pursuing a degree or program in Computer Science, Engineering, Mathematics, Statistics or relevant field to the role. | https://boards.greenhouse.io/cloudflare/jobs/8245211?gh_jid=8245211 |
| 7 | Ramp | Software Engineering Intern, iOS | reject correct | - Currently pursuing a BS or higher in Computer Science or a related technical field, graduating December 2027 or later | https://jobs.ashbyhq.com/ramp/b66be397-240b-41a6-9b05-493299b270a9 |
| 8 | Ramp | Software Engineering Intern, Backend | reject correct | - Currently pursuing a BS or higher in Computer Science or a related technical field, graduating December 2027 or later | https://jobs.ashbyhq.com/ramp/acf6b28d-767f-483f-8ff2-114620cd7e04 |
| 9 | Zoox | Safety Reporting Intern [Summer 2027] | reject correct | Currently pursuing a Master’s degree (or advanced degree) in Automotive Safety, Robotics, Mechanical Engineering, Systems Engineering, Data Analytics, or related technical discipline. | https://jobs.lever.co/zoox/614f35d6-a415-4f44-be38-cb38877df1db |
| 10 | Ramp | Software Engineering Intern, Frontend | reject correct | - Currently pursuing a BS or higher in Computer Science or a related technical field, graduating December 2027 or later | https://jobs.ashbyhq.com/ramp/a13ae586-f4cb-4385-8822-c42b9b54ed74 |

## `GRADUATION_YEAR_MISMATCH`

| No | Company | Title | Verdict on the reject | Evidence | Posting |
|----|---------|-------|-----------------------|----------|---------|
| 1 | Palantir | Privacy and Civil Liberties Software Engineer, Internship | reject correct | Must be planning on graduating in 2027. | https://jobs.lever.co/palantir/09846827-b931-4a9f-bd64-c3bb8860187b |
| 2 | Datadog | Software Engineering Intern | reject correct | Expected to graduate in 2027 with a degree in Computer Science, Software Engineering, or a related technical field from a university in Spain | https://careers.datadoghq.com/detail/8114161/?gh_jid=8114161 |
| 3 | Palantir | Forward Deployed Software Engineer, Internship - US Government | reject correct | Must be planning on graduating in 2027. | https://jobs.lever.co/palantir/315f695d-04d1-4a9a-848e-cb2bec7a997e |
| 4 | Palantir | Forward Deployed Software Engineer, Internship - Commercial | reject correct | Must be graduating in 2027 or 2028. | https://jobs.lever.co/palantir/2ad0ab10-34c3-410d-883b-8052864a95cd |
| 5 | Palantir | Forward Deployed Software Engineer, Internship - US Government | reject correct | Must be planning on graduating in 2028. | https://jobs.lever.co/palantir/e0010393-c300-446f-bf67-fa2ef067f16f |
| 6 | Datadog | Applied Science Intern | reject correct | You will graduate in 2027 with a degree in Machine Learning, Artificial Intelligence, Statistics, Computer Science, or a related field | https://careers.datadoghq.com/detail/8181440/?gh_jid=8181440 |
| 7 | Palantir | Software Engineer, Internship - Data Connectors | reject correct | Must be planning on graduating in 2028. | https://jobs.lever.co/palantir/45e4617d-d658-4b30-8dc9-378ca84a027a |
| 8 | Datadog | IT Support Technician Intern | reject correct | You will graduate in 2027 with a degree in IT, Cybersecurity field | https://careers.datadoghq.com/detail/8129799/?gh_jid=8129799 |
| 9 | Palantir | Product Designer, Internship | reject correct | Must be planning on graduating in 2028. | https://jobs.lever.co/palantir/44129013-01e0-4699-8fc1-7a189bb37b63 |
| 10 | Palantir | Forward Deployed Software Engineer, Internship - US Government | reject correct | Must be planning on graduating in 2028. | https://jobs.lever.co/palantir/e6ff8bf2-135e-474d-ad37-24f490ae1dd2 |

## Limits

- **Not reviewed by a human yet.** The sample was drawn and judged by the AI assistant only. The
  repository owner has not read these 20 decisions, so no row has an independent human check.
- **The sample is narrow.** It comes from a handful of companies (Zoox, Ramp, Notion, Datadog,
  Cloudflare, Palantir) and many rows repeat the same sentence (for example three Ramp postings
  share one sentence and several Palantir postings share "Must be planning on graduating in 2028.").
  20 rows say little about how the rules behave on other wording or other companies.
- **It checks precision only.** It asks whether the rejections that were drawn look right. It does
  not look at postings the rules missed (recall): a posting that states a student requirement or a
  graduation year in wording the rules do not recognise would not appear here at all.
- **It is not an accuracy claim.** The rows are not a random sample of all postings, and the
  labelled sets in `tests/data/` are still unverified. These counts must not be quoted as a
  measure of how good the filter is.
- **It judges a sentence, not a posting.** Each row was judged on the stored evidence sentence and
  the title, against one fictional profile. A different profile (for example `student_status:
  enrolled`) would change what is rejected.
