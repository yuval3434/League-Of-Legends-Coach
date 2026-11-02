import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from fakes import FakeModel, calls, says
from test_analytics import add_game
from ingestion.models import Player
from main import create_app


@pytest.fixture
def client(test_settings):
    settings = test_settings.model_copy(update={"riot_api_key": SecretStr("")})
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_health_checks_the_database(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_sync_without_a_key_is_refused(client):
    response = client.post("/sync", json={"game_name": "a", "tag_line": "b"})

    assert response.status_code == 503


def test_status_starts_idle(client):
    assert client.get("/sync/status").json() == {"state": "idle"}


def test_second_sync_is_refused_while_one_runs(test_settings):
    settings = test_settings.model_copy(update={"riot_api_key": SecretStr("key")})
    with TestClient(create_app(settings)) as client:
        client.app.state.sync_status = {"state": "running"}

        response = client.post("/sync", json={"game_name": "a", "tag_line": "b"})

    assert response.status_code == 409


def coach_client(test_settings, model):
    return TestClient(create_app(test_settings, coach_model=model))


async def add_player(sessions):
    async with sessions() as session:
        session.add(
            Player(puuid="me", game_name="a", tag_line="b", region="euw1", raw_account={})
        )
        await session.commit()


def test_tests_never_hold_a_model_key(test_settings):
    assert test_settings.anthropic_api_key.get_secret_value() == ""


def test_the_coach_without_a_key_is_refused(client):
    response = client.post("/coach", json={"question": "How am I doing?"})

    assert response.status_code == 503
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]


async def test_the_coach_needs_a_synced_player(test_settings, sessions):
    with coach_client(test_settings, FakeModel(says("Hi."))) as client:
        response = client.post("/coach", json={"question": "How am I doing?"})

    assert response.status_code == 409


async def test_the_coach_answers_with_its_status_and_usage(test_settings, sessions):
    await add_player(sessions)
    with coach_client(test_settings, FakeModel(says("Play more games."))) as client:
        response = client.post("/coach", json={"question": "How am I doing?"})

    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "Play more games."
    assert body["status"] == "verified"
    assert body["usage"]["input_tokens"] == 100
    assert "tool_log" not in body


async def test_a_made_up_number_reaches_the_user_with_a_warning(test_settings, sessions):
    await add_player(sessions)
    model = FakeModel(says("You win 99% of games."), says("You win 98% of games."))
    with coach_client(test_settings, model) as client:
        body = client.post("/coach", json={"question": "Win rate?"}).json()

    assert body["status"] == "unverified"
    assert body["text"].startswith("Warning:")


def test_an_empty_question_is_refused(client):
    assert client.post("/coach", json={"question": ""}).status_code == 422


async def test_the_coach_lists_each_tools_sample_sizes(test_settings, sessions):
    await add_player(sessions)
    async with sessions() as session:
        await add_game(session, "EUW1_1")
        await session.commit()
    model = FakeModel(calls(("win_rates", {"champion": None})), says("Play more games."))
    with coach_client(test_settings, model) as client:
        body = client.post("/coach", json={"question": "Win rate?"}).json()

    [tool] = body["tools"]
    assert tool["name"] == "win_rates"
    assert tool["your_games"] == {"min": 1, "max": 1}
    assert tool["low_sample_rows"] == 2


async def test_a_stat_runs_without_a_model_key(test_settings, sessions):
    await add_player(sessions)
    async with sessions() as session:
        await add_game(session, "EUW1_1")
        await session.commit()
    with TestClient(create_app(test_settings)) as client:
        response = client.get("/stats/win_rates")

    assert response.status_code == 200
    assert {row["dimension"] for row in response.json()["rows"]} == {"champion", "role"}


async def test_a_stat_can_be_narrowed_to_a_champion(test_settings, sessions):
    await add_player(sessions)
    async with sessions() as session:
        await add_game(session, "EUW1_1", champion="Viego")
        await add_game(session, "EUW1_2", champion="Quinn")
        await session.commit()
    with TestClient(create_app(test_settings)) as client:
        rows = client.get("/stats/win_rates", params={"champion": "Viego"}).json()["rows"]

    assert {row["value"] for row in rows if row["dimension"] == "champion"} == {"Viego"}


def test_an_unknown_stat_is_404(client):
    assert client.get("/stats/no_such_stat").status_code == 404


async def test_a_bad_argument_is_422(test_settings, sessions):
    await add_player(sessions)
    with TestClient(create_app(test_settings)) as client:
        response = client.get("/stats/compare_to_benchmark", params={"cohort": "gold"})

    assert response.status_code == 422
