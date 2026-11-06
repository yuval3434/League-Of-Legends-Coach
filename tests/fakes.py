"""A scripted model, so the loop can be tested without any paid calls."""

from typing import Any

from agent.llm import ModelReply, ToolCall, Usage


def says(text: str, stop_reason: str = "end_turn") -> ModelReply:
    return ModelReply(
        text,
        [],
        stop_reason,
        [{"type": "text", "text": text}],
        Usage(input_tokens=100, output_tokens=10),
        "fake-model",
    )


def calls(*tools: tuple[str, dict[str, Any]]) -> ModelReply:
    tool_calls = [
        ToolCall(f"call_{n}", name, arguments)
        for n, (name, arguments) in enumerate(tools)
    ]
    content = [
        {"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments}
        for c in tool_calls
    ]
    return ModelReply(
        "",
        tool_calls,
        "tool_use",
        content,
        Usage(input_tokens=100, output_tokens=10),
        "fake-model",
    )


class FakeModel:
    """Plays back its replies in order and keeps what it was sent."""

    def __init__(self, *replies: ModelReply) -> None:
        self.replies = list(replies)
        self.sent: list[list[dict[str, Any]]] = []
        self.system = ""
        self.tools: list[dict[str, Any]] = []
        self.max_tokens: list[int] = []

    async def send(
        self,
        system: str,
        tools: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        max_tokens: int = 16_000,
    ) -> ModelReply:
        self.system = system
        self.tools = tools
        self.max_tokens.append(max_tokens)
        self.sent.append(list(messages))
        return self.replies.pop(0)
