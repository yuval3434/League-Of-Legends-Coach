"""The agent loop, with a fake model and fake tools: no database, no paid calls."""

import json

import pytest
from fakes import FakeModel, calls, says

import agent.coach as coach
from agent.coach import MAX_STEPS, ask_coach
from agent.llm import Usage
from agent.prompt import SYSTEM_PROMPT
from agent.tools import ToolResult

GOLD = json.dumps({"games": 30, "avg_gold": 3584.0})
ASK = ("gold_cs_at_minute", {"champion": None})


@pytest.fixture(autouse=True)
def fake_tools(monkeypatch):
    """Tools answer with GOLD. `tools_run` records what was called."""
    tools_run = []

    async def run_tool(context, name, arguments):
        tools_run.append(name)
        if name == "broken":
            return ToolResult("This tool failed.", is_error=True)
        return ToolResult(GOLD)

    monkeypatch.setattr(coach, "run_tool", run_tool)
    return tools_run


async def ask(*replies):
    model = FakeModel(*replies)
    return model, await ask_coach(model, None, "How's my gold?")


async def test_an_answer_with_real_numbers_is_verified():
    model, answer = await ask(calls(ASK), says("You average 3584 gold over 30 games."))
    assert answer.status == "verified"
    assert answer.text == "You average 3584 gold over 30 games."
    assert answer.caught_numbers == []
    assert len(model.sent) == 2


async def test_the_system_prompt_is_sent():
    model, _ = await ask(says("Nothing to report."))
    assert model.system == SYSTEM_PROMPT


async def test_a_made_up_number_gets_one_retry_that_names_it():
    model, answer = await ask(
        calls(ASK),
        says("You average 9999 gold."),
        says("You average 3584 gold over 30 games."),
    )
    assert answer.status == "verified"
    assert answer.text == "You average 3584 gold over 30 games."
    assert answer.caught_numbers == ["9999"]
    retry = model.sent[-1][-1]
    assert retry["role"] == "user"
    assert "9999" in retry["content"]


async def test_the_retry_can_call_a_tool():
    _, answer = await ask(
        says("You average 3584 gold."),
        calls(ASK),
        says("You average 3584 gold over 30 games."),
    )
    assert answer.status == "verified"
    assert answer.caught_numbers == ["3584"]


async def test_a_second_bad_reply_is_shown_with_a_warning():
    model, answer = await ask(
        calls(ASK), says("You average 9999 gold."), says("You average 8888 gold.")
    )
    assert answer.status == "unverified"
    assert answer.text.startswith("Warning:")
    assert "8888" in answer.text.split("\n")[0]
    assert answer.caught_numbers == ["9999", "8888"]
    assert model.replies == []


async def test_an_answer_that_skipped_the_tools_is_caught():
    _, answer = await ask(says("You average 3584 gold."), says("You're doing fine."))
    assert answer.status == "verified"
    assert answer.caught_numbers == ["3584"]


async def test_the_retry_budget_covers_the_whole_answer():
    """After a retry, a later bad reply gets a warning, not a second retry."""
    model, answer = await ask(
        says("You average 9999 gold."),
        calls(ASK),
        says("You average 7777 gold."),
    )
    assert answer.status == "unverified"
    assert model.replies == []


async def test_a_failed_tool_gives_no_support_for_numbers(fake_tools):
    _, answer = await ask(
        calls(("broken", {})),
        says("You average 3584 gold."),
        says("I couldn't get that data."),
    )
    assert answer.caught_numbers == ["3584"]
    assert answer.status == "verified"


async def test_an_error_goes_back_to_the_model_marked_as_one():
    model, _ = await ask(calls(("broken", {})), says("I couldn't get that data."))
    result = model.sent[1][-1]["content"][0]
    assert result["is_error"] is True


async def test_parallel_calls_answer_in_one_message_with_matching_ids(fake_tools):
    model, answer = await ask(
        calls(ASK, ("win_rates", {"champion": None})), says("Nothing to report.")
    )
    message = model.sent[1][-1]
    assert message["role"] == "user"
    assert [r["tool_use_id"] for r in message["content"]] == ["call_0", "call_1"]
    assert answer.tools_called == ["gold_cs_at_minute", "win_rates"]
    assert sorted(fake_tools) == ["gold_cs_at_minute", "win_rates"]


async def test_the_models_own_blocks_go_back_unchanged():
    reply = calls(ASK)
    model, _ = await ask(reply, says("Nothing to report."))
    assert model.sent[1][1] == {"role": "assistant", "content": reply.assistant_content}


async def test_a_refusal_stops_without_showing_partial_text():
    _, answer = await ask(says("Half an answer", stop_reason="refusal"))
    assert answer.status == "refused"
    assert "Half an answer" not in answer.text


async def test_a_cut_off_reply_stops_without_showing_partial_text():
    _, answer = await ask(says("You average 3584", stop_reason="max_tokens"))
    assert answer.status == "truncated"
    assert "3584" not in answer.text


async def test_a_model_that_never_stops_calling_tools_is_stopped():
    model, answer = await ask(*[calls(ASK) for _ in range(MAX_STEPS)])
    assert answer.status == "gave_up"
    assert len(model.sent) == MAX_STEPS


async def test_usage_adds_up_across_turns():
    _, answer = await ask(calls(ASK), says("Nothing to report."))
    assert answer.usage == Usage(input_tokens=200, output_tokens=20)
