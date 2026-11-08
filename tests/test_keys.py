"""API keys: kept in .env, tested before saving, and never read back out."""

import logging
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from ingestion.keys import describe, key_problem, read_env, save_key, write_env
from ingestion.riot_client import RiotAuthError
from main import create_app

RIOT_KEY = "RGAPI-11111111-2222-3333-4444-5555abcd"
NEW_RIOT_KEY = "RGAPI-99999999-8888-7777-6666-5555wxyz"
HEADERS = {"X-LoLCoach-Settings": "1"}

ENV = """# Copy to .env. Never commit .env.
RIOT_API_KEY=old-key-0000
# The coach.
COACH_MODEL=claude-opus-5-5
POSTGRES_HOST=localhost
"""


# The .env file


def test_write_env_changes_only_the_named_lines(tmp_path):
    path = tmp_path / ".env"
    path.write_text(ENV, encoding="utf-8")

    write_env(path, {"RIOT_API_KEY": RIOT_KEY, "RIOT_API_KEY_SET_AT": "2026-11-03T10:00:00+00:00"})

    assert path.read_text(encoding="utf-8") == ENV.replace("old-key-0000", RIOT_KEY) + (
        "RIOT_API_KEY_SET_AT=2026-11-03T10:00:00+00:00\n"
    )


def test_write_env_keeps_windows_line_endings(tmp_path):
    path = tmp_path / ".env"
    path.write_bytes(ENV.replace("\n", "\r\n").encode())

    write_env(path, {"RIOT_API_KEY": RIOT_KEY})

    text = path.read_bytes().decode()
    assert "\r\n" in text and "\n" not in text.replace("\r\n", "")
    assert read_env(path)["COACH_MODEL"] == "claude-opus-5-5"


def test_a_key_is_described_by_its_last_4_characters_only(tmp_path):
    path = tmp_path / ".env"
    save_key(path, "riot", RIOT_KEY, now=datetime(2026, 11, 3, 10, tzinfo=UTC))

    info = describe(path, "riot")

    assert info == {
        "set": True,
        "last4": "abcd",
        "set_at": "2026-11-03T10:00:00+00:00",
        # Development keys last 24 hours.
        "expires_at": "2026-11-04T10:00:00+00:00",
    }
    assert RIOT_KEY not in str(info)


def test_an_unset_key_shows_nothing(tmp_path):
    info = describe(tmp_path / ".env", "anthropic")
    assert info == {"set": False, "last4": None, "set_at": None}


@pytest.mark.parametrize(
    "bad",
    [
        "RGAPI-1111 2222",
        "RGAPI-1111\t2222",
        "RGAPI-1111\nPOSTGRES_HOST=evil",
        "RGAPI-1111\r\n2222",
        "RGAPI-1111=2222",
    ],
)
def test_a_key_with_whitespace_a_newline_or_equals_is_refused_and_not_written(tmp_path, bad):
    path = tmp_path / ".env"
    path.write_text(ENV, encoding="utf-8")
    assert key_problem(bad) is not None
    with pytest.raises(ValueError) as refused:
        save_key(path, "riot", bad)
    assert bad not in str(refused.value)
    assert path.read_text(encoding="utf-8") == ENV


def test_a_normal_key_has_no_problem():
    assert key_problem(RIOT_KEY) is None
    assert key_problem("sk-ant-api03-abc_DEF-123") is None


# The endpoints


@pytest.fixture
def env(tmp_path):
    path = tmp_path / ".env"
    path.write_text(ENV, encoding="utf-8")
    return path


def client_for(test_settings, env, refuse=False):
    async def tester(key):
        if refuse:
            raise RiotAuthError("Riot returned 401.")

    app = create_app(test_settings, env_path=env, key_testers={"riot": tester, "anthropic": tester})
    return TestClient(app, base_url="http://localhost")


def test_a_tested_key_is_saved_and_never_returned(test_settings, env, caplog):
    caplog.set_level(logging.DEBUG)
    with client_for(test_settings, env) as client:
        saved = client.put("/settings/keys/riot", json={"key": NEW_RIOT_KEY}, headers=HEADERS)
        listed = client.get("/settings/keys", headers=HEADERS)

    assert saved.status_code == 200
    assert read_env(env)["RIOT_API_KEY"] == NEW_RIOT_KEY
    assert saved.json()["last4"] == "wxyz"
    assert listed.json()["riot"]["last4"] == "wxyz"
    for text in (saved.text, listed.text, caplog.text):
        assert NEW_RIOT_KEY not in text


def test_a_refused_key_isnt_saved(test_settings, env, caplog):
    caplog.set_level(logging.DEBUG)
    with client_for(test_settings, env, refuse=True) as client:
        response = client.put("/settings/keys/riot", json={"key": NEW_RIOT_KEY}, headers=HEADERS)

    assert response.status_code == 400
    assert "wasn't saved" in response.json()["detail"]
    assert read_env(env)["RIOT_API_KEY"] == "old-key-0000"
    assert NEW_RIOT_KEY not in response.text
    # The log says what Riot answered, so a refusal can be diagnosed; never the key.
    assert "refused on its test call: Riot returned 401." in caplog.text
    assert NEW_RIOT_KEY not in caplog.text


def test_the_new_key_is_used_without_a_restart(test_settings, env):
    with client_for(test_settings, env) as client:
        old = client.app.state.riot
        client.put("/settings/keys/riot", json={"key": NEW_RIOT_KEY}, headers=HEADERS)
        assert client.app.state.riot is not old
        assert client.app.state.riot._http.headers["X-Riot-Token"] == NEW_RIOT_KEY


def test_a_key_in_env_wins_over_the_containers_environment(test_settings, env):
    # The container was created with an old key; the settings page saved a new one.
    save_key(env, "riot", NEW_RIOT_KEY)
    with client_for(test_settings, env) as client:
        assert client.app.state.riot._http.headers["X-Riot-Token"] == NEW_RIOT_KEY


@pytest.mark.parametrize(
    ("base_url", "headers"),
    [
        ("http://localhost", {}),  # no header: another site's page can't send it unasked
        ("http://evil.example", HEADERS),  # a name that points at us, but isn't ours
        ("http://192.168.1.20", HEADERS),
    ],
)
def test_settings_answer_only_this_computers_app(test_settings, env, base_url, headers):
    app = create_app(test_settings, env_path=env, key_testers={})
    with TestClient(app, base_url=base_url) as client:
        assert client.get("/settings/keys", headers=headers).status_code == 403
        assert client.put("/settings/keys/riot", json={"key": NEW_RIOT_KEY}, headers=headers).status_code == 403
    assert read_env(env)["RIOT_API_KEY"] == "old-key-0000"


def test_the_riot_key_cant_change_during_a_sync(test_settings, env):
    with client_for(test_settings, env) as client:
        client.app.state.sync_status = {"state": "running"}
        response = client.put("/settings/keys/riot", json={"key": NEW_RIOT_KEY}, headers=HEADERS)

    assert response.status_code == 409
    assert read_env(env)["RIOT_API_KEY"] == "old-key-0000"


def test_without_a_env_file_key_settings_are_off(test_settings):
    with TestClient(create_app(test_settings), base_url="http://localhost") as client:
        assert client.get("/settings/keys", headers=HEADERS).status_code == 503
