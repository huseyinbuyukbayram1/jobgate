"""Read and validate the companies file (which boards to fetch)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, get_args

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from jobgate.models import AtsName

SUPPORTED_SOURCES: tuple[str, ...] = get_args(AtsName)
Region = Literal["global", "eu"]


class ConfigError(Exception):
    """The companies file is missing, unreadable or invalid."""


class Company(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    ats: AtsName
    token: str = Field(min_length=1, description="Board token / site name used in the ATS URL")
    enabled: bool = True
    region: Region = "global"  # only Lever has a separate EU host (api.eu.lever.co)

    @model_validator(mode="after")
    def _region_only_for_lever(self) -> Company:
        if self.region != "global" and self.ats != "lever":
            raise ValueError(f"region: {self.region} is only supported for lever, not {self.ats}")
        return self


class CompanyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: dict[AtsName, bool] = Field(
        default_factory=lambda: {name: True for name in SUPPORTED_SOURCES}
    )
    companies: list[Company] = Field(default_factory=list)

    @model_validator(mode="after")
    def _fill_sources_and_check_duplicates(self) -> CompanyConfig:
        for name in SUPPORTED_SOURCES:
            self.sources.setdefault(name, True)  # type: ignore[arg-type]
        seen: set[tuple[str, str, str]] = set()
        for company in self.companies:
            key = (company.ats, company.token.lower(), company.region)
            if key in seen:
                raise ValueError(f"duplicate company board: {company.ats}/{company.token}")
            seen.add(key)
        return self

    def active_companies(self) -> list[Company]:
        """Companies that are enabled and whose source is switched on."""
        return [c for c in self.companies if c.enabled and self.sources.get(c.ats, True)]


def load_companies(path: Path | str) -> CompanyConfig:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(f"companies file not found: {path}") from None
    except OSError as exc:
        raise ConfigError(f"cannot read companies file {path}: {exc}") from exc
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be a mapping with a 'companies' list")
    try:
        return CompanyConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"invalid companies file {path}:\n{_format_errors(exc)}") from exc


def _format_errors(exc: ValidationError) -> str:
    lines = []
    for err in exc.errors():
        where = ".".join(str(part) for part in err["loc"]) or "(root)"
        got = (
            f" (got {err['input']!r})"
            if "input" in err and not isinstance(err["input"], dict)
            else ""
        )
        lines.append(f"  - {where}: {err['msg']}{got}")
    return "\n".join(lines)
