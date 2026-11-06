"""The one place that talks to a model.

The loop in coach.py only knows ModelClient, so tests can use a fake, and a local
model is one more class here. Messages use Anthropic's shape; OllamaModel
translates them both ways, so the loop, the tools and the number check are the
same for every model.
"""

import json
import re
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from anthropic import AsyncAnthropic
from anthropic.types.beta import BetaMessage

from ingestion.config import Settings

MAX_TOKENS = 16_000

# Models that accept the API's automatic retry on another model after a refusal.
FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_read_tokens + other.cache_read_tokens,
            self.cache_write_tokens + other.cache_write_tokens,
        )


@dataclass(frozen=True)
class ModelReply:
    text: str
    tool_calls: list[ToolCall]
    stop_reason: str
    # Sent back unchanged on the next turn, because the API needs its own blocks.
    assistant_content: Any
    usage: Usage = Usage()
    # The model that answered, which a refusal fallback can change.
    model: str = ""


class ModelClient(Protocol):
    # Whether replies cite each number's field (agent/citations.py). A model
    # without it gets the plain number check.
    cites: bool

    async def send(
        self,
        system: str,
        tools: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        max_tokens: int = MAX_TOKENS,
    ) -> ModelReply: ...


class AnthropicModel:
    cites = True

    def __init__(self, client: AsyncAnthropic, model: str, effort: str) -> None:
        self._client = client
        self._model = model
        self._effort = effort

    async def send(
        self,
        system: str,
        tools: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        max_tokens: int = MAX_TOKENS,
    ) -> ModelReply:
        options: dict[str, Any] = {}
        if self._model in FALLBACK_MODELS:
            options = {"betas": [FALLBACK_BETA], "fallbacks": "default"}
        response = await self._client.beta.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            tools=tools,
            messages=messages,
            output_config={"effort": self._effort},
            cache_control={"type": "ephemeral"},
            **options,
        )
        return _to_reply(response)

    async def count_input_tokens(
        self, system: str, tools: list[dict[str, Any]], messages: list[dict[str, Any]]
    ) -> int:
        """The input tokens this request would send. Anthropic doesn't charge for it."""
        counted = await self._client.beta.messages.count_tokens(
            model=self._model, system=system, tools=tools, messages=messages
        )
        return counted.input_tokens


def _to_reply(response: BetaMessage) -> ModelReply:
    usage = response.usage
    return ModelReply(
        text="".join(b.text for b in response.content if b.type == "text"),
        tool_calls=[
            ToolCall(b.id, b.name, b.input)
            for b in response.content
            if b.type == "tool_use"
        ],
        stop_reason=response.stop_reason or "",
        model=response.model,
        assistant_content=response.content,
        usage=Usage(
            usage.input_tokens,
            usage.output_tokens,
            usage.cache_read_input_tokens or 0,
            usage.cache_creation_input_tokens or 0,
        ),
    )


# A full comparison is about 12,000 tokens, and Ollama's default context is a few
# thousand: left alone, it would silently cut tool results short.
LOCAL_CONTEXT = 32_768
LOCAL_TIMEOUT_S = 600.0
# Prefix that marks a local model in replies, pricing and the eval.
LOCAL_PREFIX = "ollama:"
THINK_TAGS = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


def _to_ollama(system: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Anthropic-shaped messages in Ollama's chat format."""
    out: list[dict[str, Any]] = [{"role": "system", "content": system}]
    names: dict[str, str] = {}
    for message in messages:
        content = message["content"]
        if isinstance(content, str):
            out.append({"role": message["role"], "content": content})
            continue
        if message["role"] == "assistant":
            calls = [b for b in content if b["type"] == "tool_use"]
            names |= {b["id"]: b["name"] for b in calls}
            out.append(
                {
                    "role": "assistant",
                    "content": "".join(b["text"] for b in content if b["type"] == "text"),
                    "tool_calls": [
                        {"function": {"name": b["name"], "arguments": b["input"]}} for b in calls
                    ],
                }
            )
            continue
        for block in content:
            if block["type"] == "tool_result":
                text = block["content"]
                if block.get("is_error"):
                    text = f"Error: {text}"
                out.append({"role": "tool", "content": text, "tool_name": names.get(block["tool_use_id"], "")})
            elif block["type"] == "text":
                out.append({"role": "user", "content": block["text"]})
    return out


def _ollama_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"],
            },
        }
        for tool in tools
    ]


class LocalModelError(Exception):
    """The local model didn't answer: Ollama is down, or refused the request."""


async def local_model_ready(url: str, model: str) -> str | None:
    """None if Ollama is running with `model` pulled, else what to do about it."""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            tags = (await client.get(f"{url.rstrip('/')}/api/tags")).json()
    except (httpx.HTTPError, ValueError):
        return "Ollama isn't running on this computer."
    names = {m.get("name", "") for m in tags.get("models", [])}
    if model not in names and f"{model}:latest" not in names:
        return f"Run: ollama pull {model}"
    return None


class OllamaModel:
    """A model running in Ollama on this computer. Free, and slower.

    Ollama doesn't enforce tool schemas the way strict mode does, so a call can
    carry a wrong argument; run_tool rejects it and the model sees the error.
    """

    # A small local model can't be relied on to cite, so it keeps the plain check.
    cites = False

    def __init__(self, url: str, model: str, http: httpx.AsyncClient | None = None) -> None:
        self._url = url.rstrip("/")
        self._model = model
        self._http = http or httpx.AsyncClient(timeout=LOCAL_TIMEOUT_S)

    async def send(
        self,
        system: str,
        tools: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        max_tokens: int = MAX_TOKENS,
    ) -> ModelReply:
        # The local model is free, so its output isn't capped below its context.
        try:
            response = await self._post(system, tools, messages)
        except httpx.HTTPStatusError as error:
            # Ollama's own message, such as a model that isn't pulled. It holds no secrets.
            raise LocalModelError(
                f"Ollama returned {error.response.status_code}: {error.response.text[:300]}"
            ) from error
        except httpx.HTTPError as error:
            raise LocalModelError(f"Couldn't reach Ollama: {type(error).__name__}") from error
        return _from_ollama(response.json(), self._model)

    async def _post(
        self, system: str, tools: list[dict[str, Any]], messages: list[dict[str, Any]]
    ) -> httpx.Response:
        response = await self._http.post(
            f"{self._url}/api/chat",
            json={
                "model": self._model,
                "messages": _to_ollama(system, messages),
                "tools": _ollama_tools(tools),
                "stream": False,
                # Thinking off: on a 4 GB GPU it doubles the wait for little gain here.
                "think": False,
                "options": {"num_ctx": LOCAL_CONTEXT},
            },
        )
        response.raise_for_status()
        return response


def _from_ollama(body: dict[str, Any], model: str) -> ModelReply:
    message = body.get("message", {})
    raw = message.get("content") or ""
    # qwen3 can reason in the answer even with thinking off, sometimes without the
    # opening tag. Only what follows the last </think> is the answer.
    if "</think>" in raw:
        raw = raw.rsplit("</think>", 1)[1]
    text = THINK_TAGS.sub("", raw).strip()
    calls = []
    for call in message.get("tool_calls") or []:
        function = call.get("function", {})
        arguments = function.get("arguments") or {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}
        calls.append(ToolCall(call.get("id") or f"call_{uuid.uuid4().hex[:12]}", function.get("name", ""), arguments))
    if body.get("done_reason") == "length":
        stop = "max_tokens"
    else:
        stop = "tool_use" if calls else "end_turn"
    # Kept in Anthropic's shape, so the loop can send it back like any other reply.
    content: list[dict[str, Any]] = [{"type": "text", "text": text}] if text else []
    content += [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments} for c in calls]
    return ModelReply(
        text=text,
        tool_calls=calls,
        stop_reason=stop,
        assistant_content=content,
        usage=Usage(body.get("prompt_eval_count", 0), body.get("eval_count", 0)),
        model=LOCAL_PREFIX + model,
    )


def create_model(settings: Settings, model: str | None = None) -> ModelClient:
    """The coach model: `model` if given, else COACH_MODEL. "local" is Ollama."""
    chosen = model or settings.coach_model
    if chosen == "local":
        return OllamaModel(settings.ollama_url, settings.local_model)
    key = settings.anthropic_api_key.get_secret_value()
    if not key:
        raise ValueError("ANTHROPIC_API_KEY isn't set in .env")
    return AnthropicModel(AsyncAnthropic(api_key=key), chosen, settings.coach_effort)
