"""Command line interface: fetch | filter | score | report | mark | run | companies validate."""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from jobgate.companies import ConfigError, load_companies
from jobgate.fetch import fetch_all
from jobgate.filters import evaluate
from jobgate.http import HttpClient
from jobgate.profile import ProfileError, load_profile
from jobgate.report import build_csv, build_markdown
from jobgate.scoring import ScoringError, load_weights, score_job
from jobgate.storage import STATUSES, Storage, StorageError

app = typer.Typer(
    help=(
        "jobgate finds public job postings, screens out application blockers and ranks the "
        "rest with an explained score. It never applies for you."
    ),
    no_args_is_help=True,
    add_completion=False,
)
companies_app = typer.Typer(help="Work with the companies file.", no_args_is_help=True)
app.add_typer(companies_app, name="companies")

DEFAULT_WEIGHTS_FILE = Path("scoring.yaml")


@dataclass
class Options:
    db: Path
    profile: Path
    companies: Path
    weights: Path | None
    cache_dir: Path
    use_cache: bool
    reports_dir: Path


def make_client(opts: Options) -> HttpClient:
    return HttpClient(cache_dir=opts.cache_dir, use_cache=opts.use_cache)


def fail(message: str, code: int = 2) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code)


@app.callback()
def main(
    ctx: typer.Context,
    db: Annotated[Path, typer.Option(help="SQLite database file.", envvar="JOBGATE_DB")] = Path(
        "jobgate.db"
    ),
    profile: Annotated[
        Path, typer.Option(help="Your profile file (see profile.example.yaml).")
    ] = Path("profile.yaml"),
    companies: Annotated[
        Path, typer.Option(help="Companies file (see companies.example.yaml).")
    ] = Path("companies.yaml"),
    weights: Annotated[
        Path | None,
        typer.Option(help="Scoring weights file. Default: scoring.yaml if it exists."),
    ] = None,
    cache_dir: Annotated[Path, typer.Option(help="Where fetched answers are cached.")] = Path(
        ".jobgate_cache"
    ),
    no_cache: Annotated[
        bool, typer.Option(help="Ignore and do not write the fetch cache.")
    ] = False,
    reports_dir: Annotated[Path, typer.Option(help="Where reports are written.")] = Path("reports"),
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Show debug logging.")] = False,
) -> None:
    """Global options go before the command, e.g. `jobgate --db my.db run`."""
    logging.basicConfig(level=logging.DEBUG if verbose else logging.ERROR)
    if weights is None and DEFAULT_WEIGHTS_FILE.exists():
        weights = DEFAULT_WEIGHTS_FILE
    ctx.obj = Options(db, profile, companies, weights, cache_dir, not no_cache, reports_dir)


def _opts(ctx: typer.Context) -> Options:
    return ctx.obj


# -- steps (shared by the single commands and by `run`) ------------------------------------


def step_fetch(opts: Options) -> bool:
    try:
        config = load_companies(opts.companies)
    except ConfigError as exc:
        fail(str(exc))
    active = config.active_companies()
    if not active:
        typer.echo("No active companies in the companies file; nothing to fetch.")
        return True
    client = make_client(opts)
    try:
        report = fetch_all(config, client)
    finally:
        client.close()
    today = date.today()
    with Storage(opts.db) as store:
        new = store.upsert_jobs(report.jobs, today)
        closed = store.deactivate_missing(
            set(report.succeeded), {job.key for job in report.jobs}, today
        )
        store.record_run(
            today, len(report.jobs), new, [f"{f.company}: {f.kind}" for f in report.failures]
        )
    typer.echo(
        f"Fetched {len(report.jobs)} postings from {report.companies_ok} of {len(active)} "
        f"companies ({new} new, {closed} no longer listed)."
    )
    for failure in report.failures:
        typer.echo(f"  FAILED {failure.company} ({failure.ats}): {failure.kind}", err=True)
    if report.companies_ok == 0:
        typer.echo("error: every company failed; nothing was fetched.", err=True)
        return False
    return True


def step_filter(opts: Options) -> None:
    try:
        profile = load_profile(opts.profile)
    except ProfileError as exc:
        fail(str(exc))
    counts: Counter[str] = Counter()
    with Storage(opts.db) as store:
        for row in store.rows():
            decision = evaluate(row.job, profile)
            store.save_decision(row.job.key, decision.verdict, decision.reasons)
            counts[decision.verdict.value] += 1
    typer.echo(
        f"Filtered {sum(counts.values())} postings: {counts['pass']} pass, "
        f"{counts['check']} check, {counts['reject']} reject."
    )


def step_score(opts: Options) -> bool:
    try:
        profile = load_profile(opts.profile)
        weights = load_weights(opts.weights)
    except (ProfileError, ScoringError) as exc:
        fail(str(exc))
    scored = 0
    with Storage(opts.db) as store:
        rows = store.rows()
        if rows and all(row.verdict is None for row in rows):
            typer.echo(
                "error: nothing has been filtered yet; run `jobgate filter` first.", err=True
            )
            return False
        for row in rows:
            if row.verdict in ("pass", "check"):
                result = score_job(row.job, profile, weights)
                store.save_score(row.job.key, result.total, result.parts, result.explain())
                scored += 1
    typer.echo(f"Scored {scored} postings.")
    return True


def step_report(opts: Options, min_score: int, limit: int | None, include_rejected: bool) -> None:
    with Storage(opts.db) as store:
        rows = store.rows()
    opts.reports_dir.mkdir(parents=True, exist_ok=True)
    markdown = build_markdown(rows, date.today(), min_score=min_score, limit=limit)
    (opts.reports_dir / "report.md").write_text(markdown, encoding="utf-8")
    (opts.reports_dir / "report.csv").write_text(
        build_csv(rows, include_rejected=include_rejected), encoding="utf-8"
    )
    ranked = sorted(
        (r for r in rows if r.verdict == "pass" and r.status != "dropped"),
        key=lambda r: (-(r.score or 0), r.job.company.lower(), r.job.title.lower()),
    )
    typer.echo(f"Wrote {opts.reports_dir / 'report.md'} and {opts.reports_dir / 'report.csv'}.")
    for row in ranked[:5]:
        typer.echo(f"  {row.explanation}  {row.job.title} @ {row.job.company}")


# -- commands ---------------------------------------------------------------------------


@app.command()
def fetch(ctx: typer.Context) -> None:
    """Fetch public postings for every active company and store them."""
    if not step_fetch(_opts(ctx)):
        raise typer.Exit(1)


@app.command("filter")
def filter_(ctx: typer.Context) -> None:
    """Apply the blocker filter (visa, citizenship, video, experience, language, location)."""
    step_filter(_opts(ctx))


@app.command()
def score(ctx: typer.Context) -> None:
    """Score postings that passed the filter (or need a check), 0-100, with a breakdown."""
    if not step_score(_opts(ctx)):
        raise typer.Exit(1)


@app.command()
def report(
    ctx: typer.Context,
    min_score: Annotated[int, typer.Option(help="Hide matches below this score.")] = 0,
    limit: Annotated[int | None, typer.Option(help="Show at most this many per section.")] = None,
    include_rejected: Annotated[
        bool, typer.Option(help="Also list rejected postings in the CSV.")
    ] = False,
) -> None:
    """Write the ranked Markdown and CSV reports."""
    step_report(_opts(ctx), min_score, limit, include_rejected)


@app.command()
def mark(
    ctx: typer.Context,
    job_id: Annotated[str, typer.Argument(help="Job id shown in the report.")],
    status: Annotated[str, typer.Argument(help=f"One of: {', '.join(STATUSES)}.")],
    note: Annotated[str, typer.Option(help="Optional note stored with the status.")] = "",
) -> None:
    """Record that you applied to a posting or dropped it."""
    opts = _opts(ctx)
    if status not in STATUSES:
        raise typer.BadParameter(f"must be one of: {', '.join(STATUSES)}", param_hint="STATUS")
    try:
        with Storage(opts.db) as store:
            key = store.mark(job_id, status, note)
    except StorageError as exc:
        fail(str(exc))
    typer.echo(f"Marked {key} as {status}.")


@app.command()
def run(
    ctx: typer.Context,
    min_score: Annotated[int, typer.Option(help="Hide matches below this score.")] = 0,
    limit: Annotated[int | None, typer.Option(help="Show at most this many per section.")] = None,
) -> None:
    """Run fetch, filter, score and report in order."""
    opts = _opts(ctx)
    if not step_fetch(opts):
        raise typer.Exit(1)
    step_filter(opts)
    if not step_score(opts):
        raise typer.Exit(1)
    step_report(opts, min_score, limit, include_rejected=False)


@companies_app.command("validate")
def companies_validate(ctx: typer.Context) -> None:
    """Check the companies file and show how many companies are active."""
    opts = _opts(ctx)
    try:
        config = load_companies(opts.companies)
    except ConfigError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    active = config.active_companies()
    per_source = Counter(c.ats for c in active)
    detail = ", ".join(f"{name} {n}" for name, n in sorted(per_source.items())) or "none"
    typer.echo(f"OK: {len(config.companies)} companies, {len(active)} active ({detail}).")


if __name__ == "__main__":
    app()
