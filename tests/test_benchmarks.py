"""Benchmark pull and comparison, on a test copy of the benchmark schema."""

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, insert, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_analytics import add_frames, add_game, add_objective

import benchmarks.pull as pull
from analytics.stats import Scope, gold_cs_at_minute, overall_cs_per_minute
from benchmarks.compare import compare
from benchmarks.models import Base as BenchmarkBase
from benchmarks.models import PlayerRank, Sample, ScanQueue, create_benchmark_engine
from benchmarks.pull import Quotas, order_junglers, pull_cohort, target_champions
from factories import make_match, make_timeline
from ingestion.models import Base, Match, MatchParticipant, Player, RawResponse
from ingestion.riot_client import RiotAuthError, RiotNotFound, RiotRequestFailed
from main import create_app

ME = "me"
SILVER = "silver"
TARGETS = {"Viego"}


@pytest.fixture
async def benchmark_sessions(test_settings):
    admin = create_async_engine(test_settings.database_url)
    async with admin.begin() as connection:
        await connection.execute(text("DROP SCHEMA IF EXISTS benchmark CASCADE"))
        await connection.execute(text("CREATE SCHEMA benchmark"))
    await admin.dispose()

    engine = create_benchmark_engine(test_settings)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(BenchmarkBase.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def riot_match(match_id, blue="Viego", red="Ornn", blue_win=True, remake=False):
    """A 10-player match whose junglers are participants 2 and 7."""
    match = make_match(match_id)
    for p in match["info"]["participants"]:
        slot = (p["participantId"] - 1) % 5
        p["teamPosition"] = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")[slot]
        p["win"] = (p["participantId"] <= 5) == blue_win
        p["gameEndedInEarlySurrender"] = remake
        if slot == 1:
            p["championName"] = blue if p["participantId"] == 2 else red
    return match


class FakeRiot:
    """Stands in for RiotClient, and records the calls made."""

    def __init__(self, matches=(), silver=("puuid-2", "puuid-7")):
        self.matches = {m["metadata"]["matchId"]: m for m in matches}
        self.silver = set(silver)
        self.ranks_asked = []
        self.timelines_asked = []
        self.broken = set()

    async def get_ladder_page(self, tier, division, page):
        return [
            {"puuid": f"seed-{division}-{n}", "inactive": False} for n in range(3)
        ] + [{"puuid": ME}, {"puuid": f"gone-{division}", "inactive": True}]

    async def get_match_ids(self, puuid, queue, count, start_time=None):
        self.last_start_time = start_time
        return list(self.matches)

    async def get_match(self, match_id):
        if match_id in self.broken:
            raise RiotRequestFailed(match_id)
        if match_id not in self.matches:
            raise RiotNotFound(match_id)
        return self.matches[match_id]

    async def get_timeline(self, match_id):
        self.timelines_asked.append(match_id)
        return make_timeline(match_id)

    async def get_rank(self, puuid):
        self.ranks_asked.append(puuid)
        return "SILVER" if puuid in self.silver else "GOLD"


async def run_pull(sessions, riot, max_matches=100, skip=frozenset({ME})):
    return await pull_cohort(sessions, riot, SILVER, max_matches, TARGETS, set(skip))


async def sample_rows(sessions):
    async with sessions() as session:
        return (await session.scalars(select(Sample))).all()


# Choosing a jungler


def jungler(participant_id, champion="Ornn", puuid=None):
    return {
        "participant_id": participant_id,
        "champion_name": champion,
        "puuid": puuid or f"p{participant_id}",
    }


def test_a_target_champion_goes_first():
    junglers = [jungler(2, "Ornn"), jungler(7, "Viego")]
    assert order_junglers("EUW1_1", junglers, TARGETS)[0]["participant_id"] == 7


def test_ties_are_stable_and_vary_by_match():
    junglers = [jungler(2), jungler(7)]
    picks = [
        order_junglers(f"EUW1_{n}", junglers, TARGETS)[0]["participant_id"]
        for n in range(40)
    ]
    assert picks == [
        order_junglers(f"EUW1_{n}", reversed(junglers), TARGETS)[0]["participant_id"]
        for n in range(40)
    ]
    assert set(picks) == {2, 7}


def test_the_choice_cannot_depend_on_who_won():
    won = [jungler(2) | {"win": True}, jungler(7) | {"win": False}]
    lost = [jungler(2) | {"win": False}, jungler(7) | {"win": True}]
    assert (
        order_junglers("EUW1_1", won, TARGETS)[0]["participant_id"]
        == order_junglers("EUW1_1", lost, TARGETS)[0]["participant_id"]
    )


def test_quotas_cap_each_player_per_champion():
    quotas = Quotas()
    quotas.per_player[("p2", "Viego")] = 10

    assert not quotas.wants(jungler(2, "Viego"), TARGETS)
    assert quotas.wants(jungler(7, "Viego"), TARGETS)


def test_past_the_overall_target_only_target_champions_are_wanted():
    quotas = Quotas(overall=500)

    assert not quotas.wants(jungler(2, "Ornn"), TARGETS)
    assert quotas.wants(jungler(2, "Viego"), TARGETS)

    quotas.per_champion["Viego"] = 100
    assert not quotas.wants(jungler(2, "Viego"), TARGETS)


# The pull


async def test_a_match_gives_one_jungler_with_its_timeline(benchmark_sessions):
    riot = FakeRiot([riot_match("EUW1_1", blue="Viego")])

    outcomes = await run_pull(benchmark_sessions, riot)

    rows = await sample_rows(benchmark_sessions)
    assert outcomes == {"sampled": 1}
    assert [(r.participant_id, r.champion_name, r.in_overall) for r in rows] == [
        (2, "Viego", True)
    ]
    async with benchmark_sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Match)) == 1


async def test_the_database_refuses_a_second_jungler_from_a_match(benchmark_sessions):
    row = {
        "cohort": SILVER,
        "match_id": "EUW1_1",
        "puuid": "a",
        "champion_name": "Viego",
        "in_overall": True,
    }
    async with benchmark_sessions() as session:
        await session.execute(insert(Sample), [row | {"participant_id": 2}])
        await session.commit()
        with pytest.raises(IntegrityError):
            await session.execute(
                insert(Sample), [row | {"participant_id": 7, "puuid": "b"}]
            )


async def test_a_jungler_from_another_tier_is_passed_over(benchmark_sessions):
    riot = FakeRiot([riot_match("EUW1_1", blue="Viego")], silver={"puuid-7"})

    await run_pull(benchmark_sessions, riot)

    assert [r.participant_id for r in await sample_rows(benchmark_sessions)] == [7]


async def test_no_silver_jungler_means_no_sample_and_no_timeline(benchmark_sessions):
    riot = FakeRiot([riot_match("EUW1_1")], silver=set())

    outcomes = await run_pull(benchmark_sessions, riot)

    assert outcomes == {"no_fit": 1}
    assert riot.timelines_asked == []


async def test_ranks_are_looked_up_once(benchmark_sessions):
    riot = FakeRiot([riot_match("EUW1_1"), riot_match("EUW1_2")], silver=set())

    await run_pull(benchmark_sessions, riot)

    assert sorted(riot.ranks_asked) == ["puuid-2", "puuid-7"]
    async with benchmark_sessions() as session:
        assert await session.scalar(select(func.count()).select_from(PlayerRank)) == 2


async def test_a_match_with_the_tracked_player_is_not_used(benchmark_sessions):
    riot = FakeRiot([riot_match("EUW1_1")])

    outcomes = await run_pull(benchmark_sessions, riot, skip={"puuid-3"})

    assert outcomes == {"tracked_player": 1}
    assert riot.ranks_asked == []


async def test_remakes_are_not_used(benchmark_sessions):
    outcomes = await run_pull(
        benchmark_sessions, FakeRiot([riot_match("EUW1_1", remake=True)])
    )
    assert outcomes == {"remake": 1}


async def test_a_missing_match_is_recorded_and_not_refetched(benchmark_sessions):
    riot = FakeRiot([riot_match("EUW1_1")])
    del riot.matches["EUW1_1"]
    async with benchmark_sessions() as session:
        await session.execute(
            insert(ScanQueue), [{"cohort": SILVER, "match_id": "EUW1_1"}]
        )
        await session.commit()

    assert await run_pull(benchmark_sessions, riot, max_matches=1) == {"not_found": 1}


async def test_max_matches_stops_and_a_later_run_carries_on(benchmark_sessions):
    riot = FakeRiot([riot_match(f"EUW1_{n}") for n in range(5)])

    first = await run_pull(benchmark_sessions, riot, max_matches=2)
    second = await run_pull(benchmark_sessions, riot, max_matches=5)

    assert sum(first.values()) == 2
    assert sum(second.values()) == 5
    assert len(await sample_rows(benchmark_sessions)) == 5


async def test_a_failed_fetch_stays_queued(benchmark_sessions):
    riot = FakeRiot([riot_match("EUW1_1")])
    riot.broken = {"EUW1_1"}

    assert await run_pull(benchmark_sessions, riot) == {}

    riot.broken = set()
    assert await run_pull(benchmark_sessions, riot) == {"sampled": 1}


async def test_an_expired_key_stops_the_pull(benchmark_sessions):
    riot = FakeRiot([riot_match("EUW1_1")])

    async def expired(puuid, queue, count, start_time=None):
        raise RiotAuthError("expired")

    riot.get_match_ids = expired

    with pytest.raises(RiotAuthError):
        await run_pull(benchmark_sessions, riot)


async def test_only_the_last_28_days_are_listed(benchmark_sessions, monkeypatch):
    monkeypatch.setattr(pull.time, "time", lambda: 10_000_000)
    riot = FakeRiot([riot_match("EUW1_1")])

    await run_pull(benchmark_sessions, riot)

    assert riot.last_start_time == 10_000_000 - 28 * 86400


async def test_the_tracked_player_is_never_a_seed(benchmark_sessions):
    riot = FakeRiot([riot_match("EUW1_1")])

    await run_pull(benchmark_sessions, riot)

    async with benchmark_sessions() as session:
        rows = await session.execute(text("SELECT puuid FROM cohort_players"))
        seeds = {row.puuid for row in rows}
    assert ME not in seeds
    assert not any(seed.startswith("gone") for seed in seeds)


async def test_nothing_reaches_the_tracked_players_tables(sessions, benchmark_sessions):
    await run_pull(benchmark_sessions, FakeRiot([riot_match("EUW1_1")]))

    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(RawResponse)) == 0
        assert await session.scalar(select(func.count()).select_from(Match)) == 0


async def test_target_champions_need_five_jungle_games(sessions):
    async with sessions() as session:
        await session.execute(
            insert(Player),
            [
                {
                    "puuid": ME,
                    "game_name": "a",
                    "tag_line": "b",
                    "region": "europe",
                    "raw_account": {},
                }
            ],
        )
        for n in range(5):
            await add_game(session, f"EUW1_{n}", champion="Viego")
        for n in range(5, 9):
            await add_game(session, f"EUW1_{n}", champion="Ornn")
        for n in range(9, 14):
            await add_game(session, f"EUW1_{n}", champion="Shen", role="TOP")

        assert await target_champions(session) == {"Viego"}


# Scopes


async def add_sampled_game(session, match_id, puuid, champion="Viego", gold=1000, **kw):
    """Add a game and put the jungler (participant 2) in the sample."""
    await add_game(session, match_id, puuid=puuid, champion=champion, **kw)
    await add_frames(session, match_id, 10, {2: gold, 7: 0})
    await session.execute(
        insert(Sample),
        [
            {
                "cohort": SILVER,
                "match_id": match_id,
                "participant_id": 2,
                "puuid": puuid,
                "champion_name": champion,
                "in_overall": True,
            }
        ],
    )
    await session.commit()


async def test_a_cohort_scope_counts_only_the_sampled_player(benchmark_sessions):
    async with benchmark_sessions() as session:
        await add_sampled_game(session, "EUW1_1", "a")

        rows = await overall_cs_per_minute(
            session, Scope(cohort=SILVER, role="JUNGLE")
        )

    assert [r["games"] for r in rows] == [1]


async def test_a_scope_narrows_by_champion_role_and_patch(sessions):
    async with sessions() as session:
        await add_game(session, "EUW1_1", champion="Viego", patch="16.21")
        await add_game(session, "EUW1_2", champion="Ornn", patch="16.21")
        await add_game(session, "EUW1_3", champion="Viego", patch="16.6")
        await add_game(session, "EUW1_4", champion="Viego", patch="16.21", role="TOP")

        rows = await overall_cs_per_minute(
            session,
            Scope(
                puuids=(ME,), role="JUNGLE", champion="Viego", patches=("16.21",)
            ),
        )

    assert [r["games"] for r in rows] == [1]


async def test_the_overall_scope_skips_rows_outside_the_overall_target(
    benchmark_sessions,
):
    async with benchmark_sessions() as session:
        await add_sampled_game(session, "EUW1_1", "a")
        await add_sampled_game(session, "EUW1_2", "b")
        await session.execute(
            text("UPDATE sample SET in_overall = false WHERE match_id = 'EUW1_2'")
        )
        await session.commit()

        overall = await gold_cs_at_minute(session, Scope(cohort=SILVER))
        champion = await gold_cs_at_minute(
            session, Scope(cohort=SILVER, champion="Viego")
        )

    assert [r["games"] for r in overall] == [1]
    assert [r["games"] for r in champion] == [2]


# Comparison


async def fill_cohort(session, games=30, players=10, champion="Viego", gold=1000):
    for n in range(games):
        await add_sampled_game(
            session, f"EUW1_{n}", f"player-{n % players}", champion, gold, patch="16.21"
        )


def find(rows, **fields):
    found = [r for r in rows if all(r.get(k) == v for k, v in fields.items())]
    assert len(found) == 1, f"{fields}: {found}"
    return found[0]


@pytest.mark.parametrize(("games", "players"), [(29, 10), (30, 9)])
async def test_below_either_floor_there_is_no_benchmark(
    sessions, benchmark_sessions, games, players
):
    async with benchmark_sessions() as bench, sessions() as mine:
        await fill_cohort(bench, games, players)

        result = await compare(mine, bench, [ME], SILVER)

    assert result["status"] == "no_benchmark"
    assert result["rows"] == []
    assert (result["benchmark_games"], result["benchmark_players"]) == (games, players)


async def test_an_empty_cohort_is_no_benchmark(sessions, benchmark_sessions):
    async with benchmark_sessions() as bench, sessions() as mine:
        result = await compare(mine, bench, [ME], "emerald")

    assert result["status"] == "no_benchmark"
    assert result["benchmark_patches"] == []


async def test_every_row_shows_both_sample_sizes(sessions, benchmark_sessions):
    async with benchmark_sessions() as bench, sessions() as mine:
        await fill_cohort(bench, gold=2000)
        await add_game(mine, "EUW1_1", patch="16.21")
        await add_frames(mine, "EUW1_1", 10, {2: 1500})

        result = await compare(mine, bench, [ME], SILVER)

    row = find(result["rows"], metric="gold_cs_at_minute", minute=10, value="avg_gold")
    assert (row["my_value"], row["my_sample"], row["my_low_sample"]) == (1500, 1, True)
    assert (row["benchmark_value"], row["benchmark_sample"]) == (2000, 30)
    assert row["status"] == "ok"
    assert all("my_sample" in r and "benchmark_sample" in r for r in result["rows"])
    assert (result["benchmark_games"], result["benchmark_players"]) == (30, 10)


async def test_a_thin_row_is_no_benchmark_rather_than_a_small_average(
    sessions, benchmark_sessions
):
    async with benchmark_sessions() as bench, sessions() as mine:
        for n in range(40):
            await add_sampled_game(
                bench, f"EUW1_{n}", f"player-{n % 10}", win=n < 35, patch="16.21"
            )
        result = await compare(mine, bench, [ME], SILVER)

    def gold_diff(outcome):
        return find(
            result["rows"],
            metric="lane_diff",
            minute=10,
            result=outcome,
            value="avg_gold_diff",
        )

    assert gold_diff("win")["status"] == "ok"
    thin = gold_diff("loss")
    assert thin["benchmark_sample"] == 5
    assert thin["status"] == "no_benchmark"
    assert thin["benchmark_value"] is None


async def test_objective_shares_rest_on_objectives_not_games(
    sessions, benchmark_sessions
):
    async with benchmark_sessions() as bench, sessions() as mine:
        await fill_cohort(bench)
        await add_objective(bench, "EUW1_0", 1000, "ELDER", 100)
        for n in range(30):
            await add_objective(bench, f"EUW1_{n}", 2000, "DRAGON", 100)
        await add_game(mine, "EUW1_1", patch="16.21")
        await add_frames(mine, "EUW1_1", 1, {})
        for ms in (1000, 2000):
            await add_objective(mine, "EUW1_1", ms, "DRAGON", 100)

        result = await compare(mine, bench, [ME], SILVER)

    def row(objective):
        return find(result["rows"], metric="objective_share", objective=objective)

    assert row("DRAGON")["sample_unit"] == "objectives"
    assert (row("DRAGON")["my_sample"], row("DRAGON")["my_low_sample"]) == (2, True)
    assert (row("DRAGON")["benchmark_sample"], row("DRAGON")["status"]) == (30, "ok")
    thin = row("ELDER")
    assert (thin["benchmark_sample"], thin["benchmark_value"]) == (1, None)
    assert thin["status"] == "no_benchmark"


async def test_silver_includes_stats_measured_against_the_opponent(
    sessions, benchmark_sessions
):
    async with benchmark_sessions() as bench, sessions() as mine:
        await fill_cohort(bench)
        result = await compare(mine, bench, [ME], SILVER)

    names = {r["metric"] for r in result["rows"]}
    assert {"lane_diff", "win_rate", "gold_cs_at_minute"} <= names
    assert any("by construction" in note for note in result["notes"])


async def test_emerald_leaves_out_stats_measured_against_the_opponent(
    sessions, benchmark_sessions
):
    async with benchmark_sessions() as bench, sessions() as mine:
        await fill_cohort(bench)
        await bench.execute(text("UPDATE sample SET cohort = 'emerald'"))
        await bench.commit()

        result = await compare(mine, bench, [ME], "emerald")

    names = {r["metric"] for r in result["rows"]}
    assert "gold_cs_at_minute" in names
    assert not names & {"lane_diff", "win_rate", "objective_share"}
    assert result["not_comparable"] == ["lane_diff", "win_rate", "objective_share"]


async def test_all_champion_comparisons_match_the_benchmark_patches(
    sessions, benchmark_sessions
):
    async with benchmark_sessions() as bench, sessions() as mine:
        await fill_cohort(bench)
        await add_game(mine, "EUW1_1", patch="16.21")
        await add_game(mine, "EUW1_2", patch="16.6")

        result = await compare(mine, bench, [ME], SILVER)

    assert find(result["rows"], metric="cs_per_minute", value="avg_cs_per_min")[
        "my_sample"
    ] == 1


async def test_champion_comparisons_use_all_my_games_and_say_so(
    sessions, benchmark_sessions
):
    async with benchmark_sessions() as bench, sessions() as mine:
        await fill_cohort(bench)
        await add_game(mine, "EUW1_1", patch="16.21", champion="Viego")
        await add_game(mine, "EUW1_2", patch="16.6", champion="Viego")
        await add_game(mine, "EUW1_3", patch="16.21", champion="Ornn")

        result = await compare(mine, bench, [ME], SILVER, champion="Viego")

    assert find(result["rows"], metric="cs_per_minute", value="avg_cs_per_min")[
        "my_sample"
    ] == 2
    assert any("16.21" in note and "all their games" in note for note in result["notes"])


# API


@pytest.fixture
def client(test_settings):
    settings = test_settings.model_copy(update={"riot_api_key": SecretStr("key")})
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_an_unknown_cohort_is_refused(client):
    response = client.post(
        "/benchmarks/pull", json={"cohort": "bronze", "max_matches": 1}
    )
    assert response.status_code == 422


def test_a_pull_is_refused_during_a_sync(client):
    client.app.state.sync_status = {"state": "running"}

    response = client.post(
        "/benchmarks/pull", json={"cohort": SILVER, "max_matches": 1}
    )

    assert response.status_code == 409


def test_a_sync_is_refused_during_a_pull(client):
    client.app.state.pull_status = {"state": "running"}

    response = client.post("/sync", json={"game_name": "a", "tag_line": "b"})

    assert response.status_code == 409
