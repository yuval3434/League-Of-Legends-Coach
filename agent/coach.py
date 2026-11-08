"""The agent loop: let the model call tools until it answers, then check the answer."""

import asyncio
from dataclasses import asdict, dataclass, field
from typing import Any

from agent.citations import PROMPT as CITATION_PROMPT
from agent.citations import RETRY as CITATION_RETRY
from agent.citations import check_citations, label
from agent.llm import MAX_TOKENS, ModelClient, ModelReply, ToolCall, Usage
from agent.numbers import check_numbers
from agent.prompt import SYSTEM_PROMPT
from agent.tools import ToolContext, ToolResult, run_tool, tool_definitions
from ingestion.players import SelectedPlayer

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
CITATION_WARNING = (
    "Warning: the check couldn't match these numbers to the coach's data, so don't "
    "trust them: {problems}."
)
STOPPED = {
    "refused": "The coach couldn't answer this question.",
    "truncated": "The coach's answer was cut off, so it wasn't shown. Try a narrower question.",
    "gave_up": "The coach couldn't finish this answer. Try a narrower question.",
    "no_answer": "The local model didn't answer; try again or use Claude.",
}


@dataclass(frozen=True)
class ToolLog:
    name: str
    arguments: dict[str, Any]
    content: str
    is_error: bool


@dataclass
class CoachAnswer:
    """`status` is verified, unverified, refused, truncated, gave_up or no_answer."""

    text: str
    status: str
    tools_called: list[str] = field(default_factory=list)
    # What the check caught, including any fixed by the retry.
    caught_numbers: list[str] = field(default_factory=list)
    usage: Usage = Usage()
    # Each model that answered a turn, and every tool call with its result.
    models: list[str] = field(default_factory=list)
    tool_log: list[ToolLog] = field(default_factory=list)
    # With citations: the reply with each cited number as a [number](cite:i)
    # link, and where each one came from. Empty for a model that doesn't cite.
    linked_text: str = ""
    citations: list[dict[str, str]] = field(default_factory=list)


async def _run_calls(
    context: ToolContext, calls: list[ToolCall], hidden: tuple[str, ...] = ()
) -> list[ToolResult]:
    async def run(call: ToolCall) -> ToolResult:
        if call.name in hidden:
            return ToolResult(f"There is no tool called {call.name}.", is_error=True)
        return await run_tool(context, call.name, call.arguments)

    return list(await asyncio.gather(*(run(c) for c in calls)))


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


def riot_id(player: SelectedPlayer) -> str:
    return f"{player.game_name}#{player.tag_line}"


async def ask_coach(
    model: ModelClient,
    context: ToolContext,
    question: str,
    hidden_tools: tuple[str, ...] = (),
    preloaded: tuple[ToolLog, ...] = (),
    offer_tools: bool = True,
    max_tokens: int = MAX_TOKENS,
) -> CoachAnswer:
    """Answer one question. A reply with unsupported numbers gets one retry.

    When the context's player isn't the owner, the question says whose games
    these are, so the reply names them instead of saying "you". The system
    prompt stays the same, so its cache still works. `hidden_tools` are left out,
    for eval cases that test what the coach does without them.

    `preloaded` are tool calls the server already ran, with their results in the
    question: they count for the number check like the model's own calls. With
    `offer_tools` off and `max_tokens` set, an answer is one call (two with the
    retry) of a known size, so its cost has a ceiling before it's sent.
    """
    cite = getattr(model, "cites", False)
    system = SYSTEM_PROMPT + (CITATION_PROMPT if cite else "")
    player = context.player if context else None
    if player and not player.is_owner:
        question = (
            f"[This question is about the player {riot_id(player)}, not the person "
            'asking. Refer to them by name, not as "you".]\n\n' + question
        )
    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
    tools = [t for t in tool_definitions() if t["name"] not in hidden_tools] if offer_tools else []
    answer = CoachAnswer("", "gave_up")
    answer.tool_log += list(preloaded)
    answer.tools_called += [log.name for log in preloaded]

    for _ in range(MAX_STEPS):
        reply: ModelReply = await model.send(system, tools, messages, max_tokens)
        answer.usage += reply.usage
        answer.models.append(reply.model)

        if reply.stop_reason == "refusal":
            return _stopped(answer, "refused")
        if reply.stop_reason == "max_tokens":
            return _stopped(answer, "truncated")

        messages.append({"role": "assistant", "content": reply.assistant_content})

        if reply.tool_calls:
            results = await _run_calls(context, reply.tool_calls, hidden_tools)
            if cite:
                # Each result's objects get refs, numbered by call in this conversation.
                first = len(answer.tool_log) + 1
                results = [
                    r if r.is_error else ToolResult(label(r.content, first + n), r.is_error)
                    for n, r in enumerate(results)
                ]
            answer.tools_called += [call.name for call in reply.tool_calls]
            answer.tool_log += [
                ToolLog(c.name, c.arguments, r.content, r.is_error)
                for c, r in zip(reply.tool_calls, results)
            ]
            messages.append(_results_message(reply.tool_calls, results))
            continue

        # A model that needs a tool to answer and called none hasn't answered, and
        # its text may be its own reasoning. Not when no tools were offered.
        if getattr(model, "needs_a_tool", False) and tools and not answer.tools_called:
            return _stopped(answer, "no_answer")

        if cite:
            checked = check_citations(
                reply.text,
                [(log.name, log.content) for log in answer.tool_log if not log.is_error],
                {t["name"]: t["description"] for t in tool_definitions() if t["name"] not in hidden_tools},
                (riot_id(player),) if player else (),
            )
            if not checked.problems:
                answer.text, answer.status = checked.text, "verified"
                answer.linked_text = checked.linked
                answer.citations = [asdict(c) for c in checked.citations]
                return answer
            if answer.caught_numbers:
                answer.caught_numbers += checked.problems
                answer.text = f"{CITATION_WARNING.format(problems='; '.join(checked.problems))}\n\n{checked.text}"
                answer.status = "unverified"
                return answer
            answer.caught_numbers += checked.problems
            messages.append(
                {"role": "user", "content": CITATION_RETRY.format(problems="; ".join(checked.problems))}
            )
            continue

        # Tool descriptions count too: they hold fixed facts, such as phase boundaries.
        outputs = [log.content for log in answer.tool_log if not log.is_error]
        # Even with no tools offered, their descriptions hold the same fixed facts;
        # a hidden tool's don't count.
        outputs += [
            tool["description"] for tool in tool_definitions() if tool["name"] not in hidden_tools
        ]
        # A Riot ID can hold digits, and the reply may name the player.
        outputs += [riot_id(player)] if player else []
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
