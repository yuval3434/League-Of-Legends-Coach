"""'Options for this draft': the coach's write-up of each of the player's
champions against the enemy team, from Riot's text about them.

The server runs draft_board and riot_notes itself and puts their results in the
question, and the model gets no tools. So an answer is one call, or two with the
number check's retry, and its cost has a ceiling that can be shown before it's
paid: the input is counted exactly, and the output is capped.

It shows; it doesn't pick. The question asks for no ranking, no pick and no claim
about who wins, and the eval's draft checks hold it to that.
"""

import json
from dataclasses import dataclass
from typing import Any

from agent.coach import ToolLog
from agent.llm import AnthropicModel, ModelClient
from agent.pricing import price_of
from agent.prompt import SYSTEM_PROMPT
from agent.tools import ToolContext, run_tool

# The button's default model; the person can pick another in the model picker.
DEFAULT_MODEL = "claude-sonnet-5-5"

# About 300 words for each of up to 10 champions, with room to spare. The local
# model isn't capped: it's free.
OPTIONS_MAX_TOKENS = 6_000

QUESTION = """\
Options for this draft. My team: {allies}. Enemy team: {enemies}. Bans: {bans}.

The results of draft_board and riot_notes for this draft are below. For each of my \
jungle champions in the board's pool that isn't picked or banned, write its general \
strengths and weaknesses against this enemy team and next to my team, from Riot's \
text in riot_notes: its abilities first, and a tip only if it agrees with them. Say \
how to play against each enemy champion where Riot's text says so. Label all of it \
as general game knowledge from Riot's text, not from my games.

Never say which champion wins, is favoured or is a good pick into another, never \
rank my champions, and don't choose one: the pick is mine. Use no number that isn't \
in these results.

{results}"""


@dataclass(frozen=True)
class Prepared:
    question: str
    preloaded: tuple[ToolLog, ...]
    # The pool champions written about: available, with 3+ games.
    champions: list[str]


def _names(champions: list[str]) -> str:
    return ", ".join(champions) if champions else "none yet"


async def prepare(context: ToolContext, board: dict[str, list[str]]) -> Prepared:
    """Run the two tools for this board. Raises ValueError on a board they refuse."""
    arguments = {key: board.get(key, []) for key in ("allies", "enemies", "bans")}
    board_result = await run_tool(context, "draft_board", arguments)
    if board_result.is_error:
        raise ValueError(board_result.content)
    pool = [
        entry["champion"]
        for entry in json.loads(board_result.content)["pool"]
        if "unavailable" not in entry
    ]
    if not pool:
        raise ValueError("None of your jungle champions with 3 or more games is available.")
    looked_up = pool + arguments["allies"] + arguments["enemies"]
    notes_arguments = {"champions": looked_up}
    notes_result = await run_tool(context, "riot_notes", notes_arguments)
    if notes_result.is_error:
        raise ValueError(notes_result.content)
    logs = (
        ToolLog("draft_board", arguments, board_result.content, False),
        ToolLog("riot_notes", notes_arguments, notes_result.content, False),
    )
    results = "\n\n".join(f"{log.name}:\n{log.content}" for log in logs)
    question = QUESTION.format(
        allies=_names(arguments["allies"]),
        enemies=_names(arguments["enemies"]),
        bans=_names(arguments["bans"]),
        results=results,
    )
    return Prepared(question, logs, pool)


def messages(prepared: Prepared) -> list[dict[str, Any]]:
    return [{"role": "user", "content": prepared.question}]


async def cost_ceiling(model: ModelClient, model_id: str, prepared: Prepared) -> dict[str, Any]:
    """What this answer costs at most, before it's sent.

    The input is counted exactly (Anthropic doesn't charge for counting). Every
    input token is priced at the dearer of the input and cache-write rates, and
    the output at the cap. The number check's one retry resends the input with
    the first reply on top, so the ceiling covers two calls.
    """
    price = price_of(model_id)
    if price is None:
        raise KeyError(model_id)
    if not isinstance(model, AnthropicModel):
        return {"input_tokens": None, "max_output_tokens": None, "max_cost_usd": 0.0}
    input_tokens = await model.count_input_tokens(SYSTEM_PROMPT, [], messages(prepared))
    per_input = max(price["input"], price["write"]) / 1_000_000
    per_output = price["output"] / 1_000_000
    first = input_tokens * per_input + OPTIONS_MAX_TOKENS * per_output
    # The retry's input is the first call's, plus its reply and a short request.
    retry_input = input_tokens + OPTIONS_MAX_TOKENS + 200
    retry = retry_input * per_input + OPTIONS_MAX_TOKENS * per_output
    return {
        "input_tokens": input_tokens,
        "max_output_tokens": OPTIONS_MAX_TOKENS,
        "max_cost_usd": round(first + retry, 4),
        "one_call_max_usd": round(first, 4),
    }
