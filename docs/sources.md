# Data sources

jobgate reads only public, unauthenticated job-board endpoints of Greenhouse, Lever
and Ashby. No HTML scraping, no login-gated pages, no bot-protection bypass.

Every endpoint below was checked two ways on 2026-11-24: by hand with `curl` against
real companies (3 per ATS or more), and against the official documentation. Where the
two disagree, the difference is listed explicitly.

All requests send an explicit `User-Agent` that points at this repository, wait at
least one second between network requests, time out, retry at most 3 times with
exponential backoff (timeouts, network errors, HTTP 429 and 5xx only), and are cached
on disk per calendar day so the same endpoint is not requested twice on one day.

## Greenhouse

- Endpoint: `GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true`
- Docs: <https://developers.greenhouse.io/job-board.html> (opened 2026-11-24: redirects to <https://docs.greenhouse.io/job-board.html>, HTTP 200)
- Checked by hand: `airbnb`, `cloudflare` (HTTP 200, JSON). `datadog` was checked with jobgate's own `fetch` on 2026-11-24 (386 postings).
- `content=true` is required to get the description (plus departments and offices).
- The description is HTML encoded as entities; `html_to_text` unescapes it.
- **Docs vs. live:** the docs list `first_published` only for the single-job endpoint. The live list response also carries it, so the adapter uses `first_published` and falls back to the documented `updated_at`.
- Rate limit: docs only say requests "may be rate limited"; no number is given.

## Lever

- Endpoint: `GET https://api.lever.co/v0/postings/{site}?mode=json`
- Docs: <https://github.com/lever/postings-api>
- Checked by hand: `spotify`, `palantir` (HTTP 200); `plaid` and `netflix` returned HTTP 404 (they do not use a public Lever board under that name, which is why the adapter treats 404 as "board not found" and does not retry).
- **Docs vs. live:** `createdAt` (epoch milliseconds) is not in the documented field table but is present in live answers; it is used for the posting date and the date is optional.
- Pagination: the docs describe `skip` and `limit` but state no default. Checked live: with no `limit`, the full list is returned (Palantir: 305 postings; asking for `skip=305` returned 0). The adapter therefore makes one request per company.
- EU-hosted sites use `api.eu.lever.co` per the docs; this is not supported yet.
- Rate limit: the docs only state a limit for application POSTs, not for the list endpoint.

## Ashby

- Endpoint: `GET https://api.ashbyhq.com/posting-api/job-board/{board_name}?includeCompensation=true`
- Docs: <https://developers.ashbyhq.com/docs/public-job-posting-api>
- Checked by hand: `ramp`, `notion`, `linear`, `openai` (HTTP 200). Some boards are large (OpenAI's answer is about 14 MB), hence the generous 60 s timeout used in the gate run.
- **Docs vs. live:** no job `id` field is documented, but live answers carry one. The adapter uses `id` and falls back to the last segment of `jobUrl`.
- Jobs with `isListed: false` are skipped.
- Rate limit: none stated.

## Terms of use

Links opened on 2026-11-24 (all HTTP 200):

| ATS | API documentation | Terms page found | Note |
|-----|-------------------|------------------|------|
| Greenhouse | <https://developers.greenhouse.io/job-board.html> | none | no terms page found for the job-board API |
| Lever | <https://github.com/lever/postings-api> | <https://www.lever.co/terms-of-service> (redirects to `/legal/terms-of-service`, "Terms of Service", last updated August 25, 2023) | customer terms; no separate terms for the public job-board API were found |
| Ashby | <https://developers.ashbyhq.com/docs/public-job-posting-api> | <https://www.ashbyhq.com/terms> (redirects to `/resources/terms`, "Ashby Customer Terms of Service") | customer terms; no separate terms for the public job-board API were found |

The Lever and Ashby pages govern those vendors' customers' use of their software. None of the
three API documentation pages links a separate terms page for the public job-board endpoints,
so nothing more is claimed here. Whether these terms apply to reading public postings is not
decided by this project; this is not legal advice. Each source can be switched off in the
companies file (`sources:`) if terms change.

## Responsible use (summary)

Documented public endpoints only; no authentication, scraping or bot-protection bypass; at least
one second between requests, timeout and at most 3 retries with back-off; explicit `User-Agent`
with the repository address; a per-day response cache; per-source switch in the companies file.
