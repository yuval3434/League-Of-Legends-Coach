"""Auto-sync: every tracked player on a timer, through the same sync as by hand."""

from fastapi.testclient import TestClient
from pydantic import SecretStr
from test_players import add_player
from test_sync import FakeRiot

from ingestion.auto_sync import SyncSettings, sync_round
from ingestion.riot_client import RiotAuthError, RiotNotFound
from main import create_app

HOW = SyncSettings("europe", [420], 100)


class TwoPlayerRiot(FakeRiot):
    """Each Riot ID has its own account, and its own match list."""

    def __init__(self, ids_by_name, missing=(), refuse=False):
        super().__init__({})
        self.ids_by_name = ids_by_name
        self.missing = set(missing)
        self.refuse = refuse

    async def get_account(self, game_name, tag_line):
        if self.refuse:
            raise RiotAuthError("Riot returned 401.")
        if game_name in self.missing:
            raise RiotNotFound(game_name)
        return {"puuid": f"puuid-{game_name}", "gameName": game_name, "tagLine": tag_line}

    async def get_match_ids(self, puuid, queue, count):
        return self.ids_by_name.get(puuid.removeprefix("puuid-"), [])[:count]

    async def aclose(self):
        pass


async def two_tracked(sessions):
    async with sessions() as session:
        await add_player(session, "puuid-Me", "Me", owner=True)
        await add_player(session, "puuid-Friend", "Friend")
        await session.commit()


async def test_a_round_syncs_every_player_and_counts_new_games(sessions):
    await two_tracked(sessions)
    riot = TwoPlayerRiot({"Me": ["EUW1_1", "EUW1_2"], "Friend": ["EUW1_3"]})

    first = await sync_round(sessions, riot, HOW)
    again = await sync_round(sessions, riot, HOW)

    assert first == {"state": "ok", "players": 2, "new_games": 3, "failed": []}
    # Nothing new: no match calls the second time.
    assert again["new_games"] == 0 and riot.calls["match"] == 3


async def test_a_refused_key_stops_the_round(sessions):
    await two_tracked(sessions)
    outcome = await sync_round(sessions, TwoPlayerRiot({}, refuse=True), HOW)
    assert outcome["state"] == "key_refused" and "set a new one in Settings" in outcome["error"]


async def test_a_player_riot_cant_find_doesnt_stop_the_others(sessions):
    await two_tracked(sessions)
    riot = TwoPlayerRiot({"Me": ["EUW1_1"]}, missing={"Friend"})

    outcome = await sync_round(sessions, riot, HOW)

    assert (outcome["state"], outcome["players"], outcome["new_games"]) == ("partly_failed", 1, 1)
    assert outcome["failed"] == ["Friend#EUW wasn't found"]


def test_auto_sync_is_off_unless_the_app_asks_for_it(test_settings):
    with TestClient(create_app(test_settings)) as client:
        assert client.get("/sync/auto").json() == {"state": "off", "every_minutes": 0}


async def test_a_round_skips_while_a_manual_sync_holds_the_lock(test_settings, sessions, monkeypatch):
    import main

    monkeypatch.setattr(main, "AUTO_SYNC_FIRST_DELAY_S", 3600)  # no round on its own
    await two_tracked(sessions)
    settings = test_settings.model_copy(update={"riot_api_key": SecretStr("RGAPI-test")})
    with TestClient(create_app(settings, auto_sync=True)) as client:
        state = client.app.state
        assert client.get("/sync/auto").json() == {"state": "waiting", "every_minutes": 30}

        async def held():
            async with state.sync_lock:
                await state.auto_sync_once()

        client.portal.call(held)
        skipped = client.get("/sync/auto").json()

        client.portal.call(state.riot.aclose)  # the real client, replaced by a fake
        state.riot = TwoPlayerRiot({"Me": ["EUW1_1"]})
        client.portal.call(state.auto_sync_once)
        done = client.get("/sync/auto").json()

    assert skipped["state"] == "skipped" and "manual sync" in skipped["error"]
    assert (done["state"], done["players"], done["new_games"], done["every_minutes"]) == ("ok", 2, 1, 30)
    assert "last_run_at" in done


async def test_without_a_key_a_round_says_so(test_settings, monkeypatch):
    import main

    monkeypatch.setattr(main, "AUTO_SYNC_FIRST_DELAY_S", 3600)
    settings = test_settings.model_copy(update={"riot_api_key": SecretStr("")})
    with TestClient(create_app(settings, auto_sync=True)) as client:
        client.portal.call(client.app.state.auto_sync_once)
        assert client.get("/sync/auto").json()["state"] == "no_key"
