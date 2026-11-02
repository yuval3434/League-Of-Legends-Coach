"""The one place that talks to a model.

The loop in coach.py only knows ModelClient, so tests can use a fake, and another
provider or a local model needs one new class here. Messages use Anthropic's shape,
so such a class would translate them.
"""

from dataclasses import dataclass
from typing import Any, Protocol

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


class ModelClient(Protocol):
    async def send(
        self, system: str, tools: list[dict[str, Any]], messages: list[dict[str, Any]]
    ) -> ModelReply: ...


class AnthropicModel:
    def __init__(self, client: AsyncAnthropic, model: str, effort: str) -> None:
        self._client = client
        self._model = model
        self._effort = effort

    async def send(
        self, system: str, tools: list[dict[str, Any]], messages: list[dict[str, Any]]
    ) -> ModelReply:
        options: dict[str, Any] = {}
        if self._model in FALLBACK_MODELS:
            options = {"betas": [FALLBACK_BETA], "fallbacks": "default"}
        response = await self._client.beta.messages.create(
            model=self._model,
            max_tokens=MAX_TOKENS,
            system=system,
            tools=tools,
            messages=messages,
            output_config={"effort": self._effort},
            cache_control={"type": "ephemeral"},
            **options,
        )
        return _to_reply(response)


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
        assistant_content=response.content,
        usage=Usage(
            usage.input_tokens,
            usage.output_tokens,
            usage.cache_read_input_tokens or 0,
            usage.cache_creation_input_tokens or 0,
        ),
    )


def create_model(settings: Settings) -> ModelClient:
    """The model named by COACH_MODEL."""
    key = settings.anthropic_api_key.get_secret_value()
    if not key:
        raise ValueError("ANTHROPIC_API_KEY isn't set in .env")
    return AnthropicModel(
        AsyncAnthropic(api_key=key), settings.coach_model, settings.coach_effort
    )
