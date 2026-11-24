import json
import logging

import httpx
import pytest

from jobgate.llm import (
    LlmConfig,
    LlmConfigError,
    LlmError,
    OllamaClient,
    OpenAICompatibleClient,
    build_prompt,
    clean_rationale,
    load_llm_config,
    make_client,
    write_rationales,
)
from jobgate.models import Job


def make_job(title="Junior Software Engineer"):
    return Job(
        company="Acme",
        title=title,
        location="Berlin, Germany",
        description="SECRET-POSTING-BODY",
        url="https://example.com/1",
        ats="greenhouse",
        ats_job_id="1",
    )


class FakeClient:
    def __init__(self, reply="Strong role and technology match.", fail=None):
        self.reply, self.fail, self.prompts = reply, fail, []

    def complete(self, prompt):
        self.prompts.append(prompt)
        if self.fail:
            raise self.fail
        return self.reply


# -- config ---------------------------------------------------------------------------------


def test_llm_is_off_by_default_and_without_a_file(tmp_path):
    assert LlmConfig().enabled is False
    assert load_llm_config(None).enabled is False
    assert load_llm_config(tmp_path / "missing.yaml").enabled is False


def test_config_file_is_parsed(tmp_path):
    path = tmp_path / "llm.yaml"
    path.write_text("llm:\n  enabled: true\n  model: tiny\n  timeout_seconds: 5\n")
    config = load_llm_config(path)
    assert (config.enabled, config.model, config.timeout_seconds) == (True, "tiny", 5)
    assert config.provider == "ollama"
    assert config.base_url == "http://localhost:11434"


@pytest.mark.parametrize(
    "text", ["llm: [1]", "llm:\n  provider: skynet", "llm:\n  enabled: maybe", ": : :"]
)
def test_bad_config_is_reported_clearly(tmp_path, text):
    path = tmp_path / "llm.yaml"
    path.write_text(text)
    with pytest.raises(LlmConfigError):
        load_llm_config(path)


def test_cloud_provider_needs_a_base_url():
    with pytest.raises(LlmConfigError, match="base_url"):
        make_client(LlmConfig(enabled=True, provider="openai_compatible", model="m"))


# -- Ollama client (no real server: httpx.MockTransport) -----------------------------------


def test_ollama_client_posts_a_non_streaming_chat_request():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"role": "assistant", "content": " Hi. "}})

    client = OllamaClient(
        LlmConfig(enabled=True, model="tiny"), transport=httpx.MockTransport(handler)
    )
    assert client.complete("prompt") == "Hi."
    assert seen["url"] == "http://localhost:11434/api/chat"
    assert seen["body"]["model"] == "tiny"
    assert seen["body"]["stream"] is False
    assert seen["body"]["messages"][-1] == {"role": "user", "content": "prompt"}


@pytest.mark.parametrize(
    "handler",
    [
        lambda r: httpx.Response(500, text="boom"),
        lambda r: httpx.Response(404, json={"error": "model 'x' not found"}),
        lambda r: httpx.Response(200, text="not json"),
        lambda r: httpx.Response(200, json={"unexpected": 1}),
        lambda r: (_ for _ in ()).throw(httpx.ConnectError("refused")),
        lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("slow")),
    ],
)
def test_ollama_failures_become_llm_error(handler):
    client = OllamaClient(LlmConfig(enabled=True), transport=httpx.MockTransport(handler))
    with pytest.raises(LlmError):
        client.complete("p")


def test_openai_compatible_client_sends_the_key_from_the_environment(monkeypatch):
    monkeypatch.setenv("MY_LLM_KEY", "k-123")
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Good fit."}}]})

    config = LlmConfig(
        enabled=True,
        provider="openai_compatible",
        base_url="https://llm.example.com/v1",
        model="m",
        api_key_env="MY_LLM_KEY",
    )
    client = OpenAICompatibleClient(config, transport=httpx.MockTransport(handler))
    assert client.complete("p") == "Good fit."
    assert seen["url"] == "https://llm.example.com/v1/chat/completions"
    assert seen["auth"] == "Bearer k-123"


def test_a_key_is_not_required(monkeypatch):
    monkeypatch.delenv("MY_LLM_KEY", raising=False)
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    config = LlmConfig(
        enabled=True, provider="openai_compatible", base_url="http://x/v1", model="m",
        api_key_env="MY_LLM_KEY",
    )  # fmt: skip
    OpenAICompatibleClient(config, transport=httpx.MockTransport(handler)).complete("p")
    assert seen["auth"] is None


# -- prompt and output hygiene --------------------------------------------------------------


def test_prompt_contains_only_the_score_facts_not_the_posting_body():
    prompt = build_prompt(make_job(), "72: role 28, technology 20, level 16, location 8")
    assert "Junior Software Engineer" in prompt and "Acme" in prompt
    assert "72: role 28, technology 20, level 16, location 8" in prompt
    assert "SECRET-POSTING-BODY" not in prompt
    assert "do not" in prompt.lower()  # tells the model not to add facts or numbers


def test_clean_rationale_makes_one_short_line():
    assert clean_rationale("  Good\n\nfit  here. ") == "Good fit here."
    assert clean_rationale("") is None
    assert clean_rationale("   \n ") is None
    assert len(clean_rationale("word " * 200)) <= 300
    assert clean_rationale("**Good** fit") == "Good fit"


# -- writing rationales: never raises, never touches decisions ------------------------------


def candidates():
    return [("acme:1", make_job("A"), "70: role 28"), ("acme:2", make_job("B"), "60: role 20")]


def test_write_rationales_saves_what_the_client_returns():
    saved = {}
    result = write_rationales(candidates(), FakeClient(), lambda k, t: saved.__setitem__(k, t))
    assert saved == {"acme:1": "Strong role and technology match.", "acme:2": saved["acme:2"]}
    assert (result.written, result.skipped, result.unavailable) == (2, 0, False)


def test_unreachable_llm_stops_after_one_failure_and_logs_a_warning(caplog):
    client = FakeClient(fail=LlmError("connection refused"))
    saved = {}
    with caplog.at_level(logging.WARNING, logger="jobgate.llm"):
        result = write_rationales(candidates(), client, lambda k, t: saved.__setitem__(k, t))
    assert saved == {}
    assert result.unavailable is True and "connection refused" in result.error
    assert len(client.prompts) == 1  # no pile of timeouts
    assert "rule-based" in caplog.text


def test_empty_reply_skips_that_posting_only():
    result = write_rationales(candidates(), FakeClient(reply="  "), lambda k, t: None)
    assert (result.written, result.skipped, result.unavailable) == (0, 2, False)


def test_example_config_loads_and_is_off():
    from pathlib import Path

    config = load_llm_config(Path(__file__).parent.parent / "llm.example.yaml")
    assert config.enabled is False and config.provider == "ollama"
