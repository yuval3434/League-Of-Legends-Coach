"""'Options for this draft': one capped call, with its cost ceiling shown first."""

import pytest
from fakes import FakeModel, says
from fastapi.testclient import TestClient
from test_agent_tools import store_champions
from test_analytics import ME, add_game
from test_benchmarks import benchmark_sessions  # noqa: F401
from test_champion_card import detail_file
from test_draft import champ

from agent.llm import AnthropicModel
from agent.options import OPTIONS_MAX_TOKENS, cost_ceiling, prepare
from agent.tools import ToolContext
from ingestion.ddragon import parse_detail
from ingestion.models import ChampionDetail
from main import create_app

BOARD = {"allies": ["Ahri"], "enemies": ["Wukong"], "bans": ["Quinn"]}


async def setup(sessions):
    """Data Dragon with Ahri, Wukong, Viego and Quinn; Viego and Quinn in my pool."""
    await store_champions(
        sessions,
        champ("Ahri", ["Mage"], 3, 8),
        champ("Viego", ["Assassin", "Fighter"], 6, 2),
        champ("Quinn", ["Marksman"], 9, 2),
    )
    async with sessions() as session:
        for champion in ("MonkeyKing", "Viego", "Ahri"):
            session.add(ChampionDetail(**parse_detail("1.0.1", detail_file(champion))))
        for champion in ("Viego", "Quinn"):
            for n in range(3):
                await add_game(session, f"EUW1_{champion}_{n}", champion=champion)
        await session.commit()


@pytest.fixture
def context(sessions, benchmark_sessions):  # noqa: F811
    return ToolContext(sessions, benchmark_sessions, (ME,))


async def test_the_question_carries_both_results_and_skips_banned_champions(context, sessions):
    await setup(sessions)
    prepared = await prepare(context, BOARD)

    assert prepared.champions == ["Viego"]  # Quinn is banned
    assert [log.name for log in prepared.preloaded] == ["draft_board", "riot_notes"]
    assert prepared.preloaded[1].arguments == {"champions": ["Viego", "Ahri", "Wukong"]}
    assert "draft_board:\n{" in prepared.question and "riot_notes:\n{" in prepared.question
    assert "never rank my champions" in prepared.question
    assert "Wait for Cyclone before engaging." in prepared.question  # Riot's tip against Wukong

    with pytest.raises(ValueError, match="only be picked once"):
        await prepare(context, {"allies": ["Ahri"], "enemies": ["Ahri"], "bans": []})


class Counted(AnthropicModel):
    def __init__(self, tokens):
        self.tokens = tokens

    async def count_input_tokens(self, system, tools, messages):
        assert tools == []
        return self.tokens


async def test_the_ceiling_covers_two_capped_calls_at_the_dearest_input_rate(context, sessions):
    await setup(sessions)
    prepared = await prepare(context, BOARD)

    ceiling = await cost_ceiling(Counted(10_000), "claude-sonnet-5-5", prepared)

    # Sonnet: input at the $2.50 cache-write rate, output $10, per million tokens.
    first = 10_000 * 2.5e-6 + OPTIONS_MAX_TOKENS * 10e-6
    retry = (10_000 + OPTIONS_MAX_TOKENS + 200) * 2.5e-6 + OPTIONS_MAX_TOKENS * 10e-6
    assert ceiling == {
        "input_tokens": 10_000,
        "max_output_tokens": OPTIONS_MAX_TOKENS,
        "max_cost_usd": round(first + retry, 4),
        "one_call_max_usd": round(first, 4),
    }
    assert (await cost_ceiling(FakeModel(), "local", prepared))["max_cost_usd"] == 0.0


async def test_the_answer_is_one_call_with_no_tools_and_a_capped_output(test_settings, sessions, benchmark_sessions):  # noqa: F811
    from test_players import add_player

    async with sessions() as session:
        await add_player(session, ME, "Me", owner=True)
    await setup(sessions)
    model = FakeModel(says("Viego (3 games): general game knowledge from Riot's text. The pick is yours."))
    with TestClient(create_app(test_settings, coach_model=model)) as client:
        estimate = client.post("/draft/options/estimate", json=BOARD)
        answer = client.post("/draft/options", json=BOARD)
        refused = client.post("/draft/options", json=BOARD | {"model": "gpt-9"})

    assert estimate.status_code == 200
    assert estimate.json()["model"] == "claude-sonnet-5-5" and estimate.json()["champions"] == ["Viego"]
    body = answer.json()
    assert body["status"] == "verified"
    assert body["tools_called"] == ["draft_board", "riot_notes"]
    assert (model.tools, model.max_tokens) == ([], [OPTIONS_MAX_TOKENS])
    assert len(model.sent) == 1
    assert refused.status_code == 422
