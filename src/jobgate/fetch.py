"""Stage 1 runner: fetch every active company, never let one failure stop the run."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field

from jobgate.adapters import ADAPTERS, Adapter
from jobgate.companies import CompanyConfig
from jobgate.http import FetchError, HttpClient
from jobgate.models import Job

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CompanyFailure:
    company: str
    ats: str
    kind: str
    message: str


@dataclass
class FetchReport:
    jobs: list[Job] = field(default_factory=list)
    failures: list[CompanyFailure] = field(default_factory=list)
    companies_ok: int = 0
    succeeded: list[tuple[str, str]] = field(default_factory=list)


def fetch_all(
    config: CompanyConfig,
    client: HttpClient,
    adapters: Mapping[str, Adapter] = ADAPTERS,
) -> FetchReport:
    report = FetchReport()
    seen: set[str] = set()
    for company in config.active_companies():
        try:
            extra = {"region": company.region} if company.region != "global" else {}
            jobs = adapters[company.ats].fetch(client, company.name, company.token, **extra)
        except FetchError as exc:
            kind, message = exc.kind, str(exc)
        except Exception as exc:  # noqa: BLE001 - one broken board must not end the run
            kind, message = "unexpected", f"{type(exc).__name__}: {exc}"
        else:
            report.companies_ok += 1
            report.succeeded.append((company.ats, company.name))
            for job in jobs:
                if job.key not in seen:
                    seen.add(job.key)
                    report.jobs.append(job)
            logger.info("%s (%s): %d postings", company.name, company.ats, len(jobs))
            continue
        logger.error("%s (%s) failed: %s", company.name, company.ats, message)
        report.failures.append(CompanyFailure(company.name, company.ats, kind, message))
    return report
