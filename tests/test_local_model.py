"""The local model through Ollama, with Ollama faked: no model runs in these tests."""

import json

import httpx
import pytest
from fakes import FakeModel, says
from fastapi.testclient import TestClient

from agent.coach import ask_coach
from agent.llm import LOCAL_PREFIX, LocalModelError, OllamaModel, Usage, _to_ollama
from agent.models import estimated_cost
from agent.pricing import answer_cost, cost
from agent.tools import tool_definitions
from main import create_app


def ollama(*replies):
    """An OllamaModel whose server plays back `replies` and keeps each request body."""
    sent = []

    def handle(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=replies[len(sent) - 1])

    http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    return OllamaModel("http://ollama", "qwen3:4b", http), sent


def tool_call(name, arguments):
    return {
        "message": {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": name, "arguments": arguments}}]},
        "done_reason": "stop",
        "prompt_eval_count": 900,
        "eval_count": 20,
    }


def text(content, done_reason="stop"):
    return {"message": {"role": "assistant", "content": content}, "done_reason": done_reason, "prompt_eval_count": 1200, "eval_count": 40}


async def test_a_tool_call_and_answer_round_trip_through_ollama():
    model, sent = ollama(tool_call("win_rates", {"champion": None}), text("You won 9 of 18."))
    tools = tool_definitions()
    messages = [{"role": "user", "content": "Win rate?"}]

    first = await model.send("SYSTEM", tools, messages)
    messages += [
        {"role": "assistant", "content": first.assistant_content},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": first.tool_calls[0].id, "content": "{\"rows\": []}", "is_error": False}]},
    ]
    second = await model.send("SYSTEM", tools, messages)

    assert (first.stop_reason, first.tool_calls[0].name) == ("tool_use", "win_rates")
    assert (second.stop_reason, second.text) == ("end_turn", "You won 9 of 18.")
    assert second.model == LOCAL_PREFIX + "qwen3:4b"
    assert second.usage == Usage(1200, 40)
    # The second request carries the whole conversation in Ollama's shape.
    roles = [m["role"] for m in sent[1]["messages"]]
    assert roles == ["system", "user", "assistant", "tool"]
    assert sent[1]["messages"][3]["tool_name"] == "win_rates"
    # The same tools, schemas unchanged, and a context long enough for a full comparison.
    assert [t["function"]["name"] for t in sent[0]["tools"]] == [t["name"] for t in tools]
    assert sent[0]["options"]["num_ctx"] >= 32_768


async def test_reasoning_without_an_opening_tag_is_dropped():
    model, _ = ollama(text("Okay, the user wants 5.45 vs 9.99.\n</think>\n\nYou average 5.45 CS per minute."))
    reply = await model.send("S", [], [{"role": "user", "content": "Hi"}])
    # The made-up 9.99 in the reasoning never reaches the number check or the reader.
    assert reply.text == "You average 5.45 CS per minute."


async def test_ollama_errors_become_local_model_errors():
    def refuse(request):
        return httpx.Response(400, json={"error": "model 'qwen3:4b' not found"})

    model = OllamaModel("http://ollama", "qwen3:4b", httpx.AsyncClient(transport=httpx.MockTransport(refuse)))
    with pytest.raises(LocalModelError, match="400.*not found"):
        await model.send("S", [], [{"role": "user", "content": "Hi"}])


async def test_think_tags_and_a_cut_off_reply_are_handled():
    model, _ = ollama(text("<think>hmm</think>Play more games.", done_reason="length"))
    reply = await model.send("S", [], [{"role": "user", "content": "Hi"}])
    assert (reply.text, reply.stop_reason) == ("Play more games.", "max_tokens")


def test_a_tool_error_reaches_the_model_marked_as_one():
    messages = [
        {"role": "user", "content": "Q"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "a", "name": "lane_diff", "input": {"champion": "Nobody"}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "a", "content": "Unknown champion", "is_error": True}]},
    ]
    assert _to_ollama("S", messages)[-1] == {"role": "tool", "content": "Error: Unknown champion", "tool_name": "lane_diff"}


async def test_the_number_check_is_the_same_for_a_local_model():
    # A small model invents a number twice: it gets the same one retry, then the warning.
    model = FakeModel(says("You win 99% of games."), says("You win 98% of games."))
    answer = await ask_coach(model, None, "Win rate?")
    assert answer.status == "unverified"
    assert answer.text.startswith("Warning:")


def test_a_local_answer_costs_nothing():
    usage = Usage(50_000, 2_000)
    assert cost(usage, LOCAL_PREFIX + "qwen3:4b") == 0.0
    assert answer_cost(usage, [LOCAL_PREFIX + "qwen3:4b"]) == (0.0, False)
    assert estimated_cost("local") == 0.0


def test_estimates_follow_each_models_price():
    opus, sonnet, haiku = (estimated_cost(m) for m in ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"))
    assert opus == pytest.approx(0.1048, abs=1e-4)
    assert opus > sonnet > haiku > 0


def test_the_model_list_says_what_can_answer(test_settings):
    settings = test_settings.model_copy(update={"ollama_url": "http://127.0.0.1:9"})  # nothing listens there
    with TestClient(create_app(settings)) as client:
        models = {m["id"]: m for m in client.get("/coach/models").json()}

    assert list(models) == ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "local"]
    assert models["claude-opus-5-5"]["reason"] == "Needs an Anthropic API key."
    assert models["local"]["estimated_cost_usd"] == 0.0
    assert models["local"]["reason"] == "Ollama isn't running on this computer."


def test_an_unknown_model_is_refused(test_settings):
    with TestClient(create_app(test_settings, coach_model=FakeModel())) as client:
        response = client.post("/coach", json={"question": "Hi", "model": "gpt-5"})
    assert response.status_code == 422
