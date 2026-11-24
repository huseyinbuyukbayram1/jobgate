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
- Docs: <https://docs.greenhouse.io/job-board.html> (the old `developers.greenhouse.io/job-board.html` redirects there with HTTP 301)
- Checked by hand: `stripe`, `airbnb`, `cloudflare` (all HTTP 200, JSON).
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

None of the three API documentation pages links a terms-of-use page for the public
job-board API, so none is claimed here. Until the owner has confirmed the relevant
terms, the README lists the API documentation links only. Each source can be switched
off in the companies file (`sources:`) if terms change.
