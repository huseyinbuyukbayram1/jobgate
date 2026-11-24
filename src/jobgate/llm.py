"""Optional LLM layer: a short, readable rationale next to the rule-based score.

The LLM never decides anything. It receives only facts the rules already produced (title,
company, location and the score breakdown), and what it returns is stored in its own
``rationale`` column and shown beside the explanation. Filter verdicts and scores are computed
before this module runs, are never passed back into it, and are not read from its output.

It is off by default. If the LLM is off, unreachable or answers badly, jobgate keeps the
rule-based explanation and carries on.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from jobgate.models import Job

log = logging.getLogger("jobgate.llm")

OLLAMA_URL = "http://localhost:11434"
MAX_RATIONALE_CHARS = 300


class LlmError(Exception):
    """The LLM could not be reached or gave an unusable answer."""


class LlmConfigError(Exception):
    """The LLM config file is invalid."""


class LlmConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    provider: Literal["ollama", "openai_compatible"] = "ollama"
    model: str = "llama3.2"
    base_url: str | None = None
    timeout_seconds: float = 30.0
    api_key_env: str | None = None  # name of an environment variable; never the key itself

    @model_validator(mode="after")
    def _default_url(self) -> LlmConfig:
        if self.base_url is None and self.provider == "ollama":
            self.base_url = OLLAMA_URL
        return self


def load_llm_config(path: Path | str | None) -> LlmConfig:
    """Read ``llm.yaml``. No file means the LLM is off."""
    if path is None or not Path(path).exists():
        return LlmConfig()
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise LlmConfigError(f"cannot read LLM config {path}: {exc}") from exc
    section = data.get("llm", {}) if isinstance(data, dict) else None
    if not isinstance(section, dict):
        raise LlmConfigError(f"invalid LLM config {path}: expected a mapping under 'llm:'")
    try:
        return LlmConfig(**section)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"])
        raise LlmConfigError(f"invalid LLM config {path}: {where}: {first['msg']}") from exc


class LlmClient(Protocol):
    def complete(self, prompt: str) -> str: ...


def _post(
    config: LlmConfig,
    url: str,
    body: dict,
    headers: dict[str, str],
    transport: httpx.BaseTransport | None,
) -> object:
    try:
        with httpx.Client(timeout=config.timeout_seconds, transport=transport) as client:
            response = client.post(url, json=body, headers=headers)
    except httpx.HTTPError as exc:
        raise LlmError(f"cannot reach {url}: {exc.__class__.__name__}: {exc}") from exc
    if response.status_code != 200:
        raise LlmError(f"{url} answered HTTP {response.status_code}")
    try:
        return response.json()
    except ValueError as exc:
        raise LlmError(f"{url} did not return JSON") from exc


class OllamaClient:
    """Local Ollama server: ``POST /api/chat`` with ``stream: false``."""

    def __init__(self, config: LlmConfig, transport: httpx.BaseTransport | None = None) -> None:
        self.config, self.transport = config, transport

    def complete(self, prompt: str) -> str:
        url = f"{(self.config.base_url or OLLAMA_URL).rstrip('/')}/api/chat"
        body = {
            "model": self.config.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        data = _post(self.config, url, body, {}, self.transport)
        try:
            return str(data["message"]["content"]).strip()  # type: ignore[index]
        except (KeyError, TypeError) as exc:
            raise LlmError("unexpected response shape from Ollama") from exc


class OpenAICompatibleClient:
    """Any server that speaks the common ``/chat/completions`` shape (a cloud API, for example).

    The API key is optional and is read from the environment variable named in the config.
    """

    def __init__(self, config: LlmConfig, transport: httpx.BaseTransport | None = None) -> None:
        self.config, self.transport = config, transport

    def complete(self, prompt: str) -> str:
        url = f"{(self.config.base_url or '').rstrip('/')}/chat/completions"
        body = {"model": self.config.model, "messages": [{"role": "user", "content": prompt}]}
        headers = {}
        key = os.environ.get(self.config.api_key_env) if self.config.api_key_env else None
        if key:
            headers["Authorization"] = f"Bearer {key}"
        data = _post(self.config, url, body, headers, self.transport)
        try:
            return str(data["choices"][0]["message"]["content"]).strip()  # type: ignore[index]
        except (KeyError, IndexError, TypeError) as exc:
            raise LlmError("unexpected response shape from the LLM server") from exc


def make_client(config: LlmConfig) -> LlmClient:
    if config.provider == "openai_compatible":
        if not config.base_url:
            raise LlmConfigError("provider 'openai_compatible' needs a base_url in the LLM config")
        return OpenAICompatibleClient(config)
    return OllamaClient(config)


def build_prompt(job: Job, explanation: str) -> str:
    """Only rule-produced facts go in: no posting body, no profile, no CV."""
    return (
        "You write one short rationale (at most two plain sentences) for a job-search tool.\n"
        "Reword the score breakdown below in plain English for a new graduate.\n"
        "Use only the facts listed. Do not add facts, numbers, advice or opinions, and do not "
        "change the score.\n\n"
        f"Job title: {job.title}\n"
        f"Company: {job.company}\n"
        f"Location: {job.location or 'unknown'}\n"
        f"Score breakdown (points per part): {explanation}\n"
    )


def clean_rationale(text: str) -> str | None:
    """One plain line, capped in length; ``None`` when nothing usable is left."""
    text = re.sub(r"[*_`#>]", "", text)
    text = " ".join(text.split())
    if not text:
        return None
    if len(text) > MAX_RATIONALE_CHARS:
        text = text[: MAX_RATIONALE_CHARS - 3].rsplit(" ", 1)[0] + "..."
    return text


@dataclass
class RationaleResult:
    written: int = 0
    skipped: int = 0
    unavailable: bool = False
    error: str = ""


def write_rationales(
    candidates: Iterable[tuple[str, Job, str]],
    client: LlmClient,
    save: Callable[[str, str], None],
) -> RationaleResult:
    """Ask the LLM for each ``(job_key, job, explanation)`` and hand the text to ``save``.

    Never raises. After the first connection-type failure it stops, so an absent Ollama costs
    one timeout, not one per posting.
    """
    result = RationaleResult()
    for key, job, explanation in candidates:
        try:
            raw = client.complete(build_prompt(job, explanation))
        except LlmError as exc:
            result.unavailable, result.error = True, str(exc)
            log.warning("LLM unavailable (%s); continuing with rule-based explanations only", exc)
            break
        text = clean_rationale(raw)
        if text is None:
            result.skipped += 1
            continue
        save(key, text)
        result.written += 1
    return result
