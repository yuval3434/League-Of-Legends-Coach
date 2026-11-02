"""The agent loop: let the model call tools until it answers, then check the answer."""

import asyncio
from dataclasses import dataclass, field
from typing import Any

from agent.llm import ModelClient, ModelReply, ToolCall, Usage
from agent.numbers import check_numbers
from agent.prompt import SYSTEM_PROMPT
from agent.tools import ToolContext, ToolResult, run_tool, tool_definitions

MAX_STEPS = 8

WARNING = (
    "Warning: the check couldn't find these numbers in the coach's data, so don't "
    "trust them: {numbers}."
)
RETRY = (
    "An automatic check found these numbers in your reply, but in no tool result: "
    "{numbers}. Every number must be copied exactly from a tool result. Call a tool "
    "if you need the data, or rewrite the reply without those numbers. Write it for "
    "the player: don't mention this check or what you changed."
)
STOPPED = {
    "refused": "The coach couldn't answer this question.",
    "truncated": "The coach's answer was cut off, so it wasn't shown. Try a narrower question.",
    "gave_up": "The coach couldn't finish this answer. Try a narrower question.",
}


@dataclass(frozen=True)
class ToolLog:
    name: str
    arguments: dict[str, Any]
    content: str
    is_error: bool


@dataclass
class CoachAnswer:
    """`status` is verified, unverified, refused, truncated or gave_up."""

    text: str
    status: str
    tools_called: list[str] = field(default_factory=list)
    # What the check caught, including any fixed by the retry.
    caught_numbers: list[str] = field(default_factory=list)
    usage: Usage = Usage()
    # Each model that answered a turn, and every tool call with its result.
    models: list[str] = field(default_factory=list)
    tool_log: list[ToolLog] = field(default_factory=list)


async def _run_calls(
    context: ToolContext, calls: list[ToolCall]
) -> list[ToolResult]:
    return list(
        await asyncio.gather(*(run_tool(context, c.name, c.arguments) for c in calls))
    )


def _results_message(calls: list[ToolCall], results: list[ToolResult]) -> dict[str, Any]:
    """Every result goes in one message, as the API expects for parallel calls."""
    return {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": call.id,
                "content": result.content,
                "is_error": result.is_error,
            }
            for call, result in zip(calls, results)
        ],
    }


async def ask_coach(
    model: ModelClient, context: ToolContext, question: str
) -> CoachAnswer:
    """Answer one question. A reply with unsupported numbers gets one retry."""
    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
    tools = tool_definitions()
    answer = CoachAnswer("", "gave_up")

    for _ in range(MAX_STEPS):
        reply: ModelReply = await model.send(SYSTEM_PROMPT, tools, messages)
        answer.usage += reply.usage
        answer.models.append(reply.model)

        if reply.stop_reason == "refusal":
            return _stopped(answer, "refused")
        if reply.stop_reason == "max_tokens":
            return _stopped(answer, "truncated")

        messages.append({"role": "assistant", "content": reply.assistant_content})

        if reply.tool_calls:
            results = await _run_calls(context, reply.tool_calls)
            answer.tools_called += [call.name for call in reply.tool_calls]
            answer.tool_log += [
                ToolLog(c.name, c.arguments, r.content, r.is_error)
                for c, r in zip(reply.tool_calls, results)
            ]
            messages.append(_results_message(reply.tool_calls, results))
            continue

        # Tool descriptions count too: they hold fixed facts, such as phase boundaries.
        outputs = [log.content for log in answer.tool_log if not log.is_error]
        outputs += [tool["description"] for tool in tools]
        unsupported = check_numbers(reply.text, outputs)
        if not unsupported:
            answer.text, answer.status = reply.text, "verified"
            return answer
        if answer.caught_numbers:
            numbers = ", ".join(unsupported)
            answer.caught_numbers += unsupported
            answer.text = f"{WARNING.format(numbers=numbers)}\n\n{reply.text}"
            answer.status = "unverified"
            return answer
        answer.caught_numbers += unsupported
        messages.append(
            {"role": "user", "content": RETRY.format(numbers=", ".join(unsupported))}
        )

    return _stopped(answer, "gave_up")


def _stopped(answer: CoachAnswer, status: str) -> CoachAnswer:
    answer.text, answer.status = STOPPED[status], status
    return answer
