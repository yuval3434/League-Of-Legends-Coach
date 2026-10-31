import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

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
