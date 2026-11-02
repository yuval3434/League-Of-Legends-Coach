"""The Anthropic adapter, against a fake HTTP server: nothing leaves this machine."""

import json

import httpx2
import pytest
from anthropic import AsyncAnthropic, DefaultAsyncHttpxClient
from pydantic import SecretStr

from agent.llm import AnthropicModel, Usage, create_model
from agent.tools import tool_definitions
from ingestion.config import Settings

RESPONSE = {
    "id": "msg_1",
    "type": "message",
    "role": "assistant",
    "model": "claude-opus-5-5",
    "content": [
        {"type": "text", "text": "Checking. "},
        {"type": "tool_use", "id": "toolu_1", "name": "win_rates", "input": {"champion": None}},
    ],
    "stop_reason": "tool_use",
    "stop_sequence": None,
    "usage": {
        "input_tokens": 11,
        "output_tokens": 22,
        "cache_read_input_tokens": 33,
        "cache_creation_input_tokens": 44,
    },
}


def model_with_fake_server(name="claude-opus-5-5"):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx2.Response(200, json=RESPONSE)

    client = AsyncAnthropic(
        api_key="test-key",
        max_retries=0,
        http_client=DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    return AnthropicModel(client, name, "medium"), requests


async def send(model):
    return await model.send(
        "Be a coach.", tool_definitions(), [{"role": "user", "content": "Hi"}]
    )


async def test_the_request_has_the_settings_we_chose():
    model, requests = model_with_fake_server()
    await send(model)
    body = json.loads(requests[0].content)
    assert body["model"] == "claude-opus-5-5"
    assert body["system"] == "Be a coach."
    assert body["output_config"] == {"effort": "medium"}
    assert body["cache_control"] == {"type": "ephemeral"}
    assert body["fallbacks"] == "default"
    assert requests[0].headers["anthropic-beta"] == "server-side-fallback-2026-07-01"
    assert all(tool["strict"] is True for tool in body["tools"])


async def test_the_model_comes_from_the_setting():
    model, requests = model_with_fake_server("claude-sonnet-5-5")
    await send(model)
    assert json.loads(requests[0].content)["model"] == "claude-sonnet-5-5"


async def test_a_model_without_fallbacks_doesnt_ask_for_them():
    model, requests = model_with_fake_server("claude-haiku-5-5")
    await send(model)
    assert "fallbacks" not in json.loads(requests[0].content)
    assert "anthropic-beta" not in requests[0].headers


async def test_a_response_becomes_a_reply():
    model, _ = model_with_fake_server()
    reply = await send(model)
    assert reply.text == "Checking. "
    assert reply.stop_reason == "tool_use"
    assert [(c.id, c.name, c.arguments) for c in reply.tool_calls] == [
        ("toolu_1", "win_rates", {"champion": None})
    ]
    assert reply.usage == Usage(11, 22, 33, 44)


def test_a_missing_key_is_a_clear_error():
    settings = Settings(anthropic_api_key=SecretStr(""), _env_file=None)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        create_model(settings)


def test_the_default_model_is_opus():
    assert Settings(_env_file=None).coach_model == "claude-opus-5-5"


def test_the_key_stays_out_of_the_settings_repr():
    settings = Settings(anthropic_api_key=SecretStr("sk-secret"), _env_file=None)
    assert "sk-secret" not in repr(settings)
