"""Stats for roles other than the jungle, and each role's comparison."""

from sqlalchemy import update
from test_analytics import ME, add_event, add_frames, add_game
from test_benchmarks import benchmark_sessions  # noqa: F401

from analytics.timeline_stats import damage_share, lane_plates, roams, solo_kills
from benchmarks.compare import compare
from benchmarks.models import Sample
from ingestion.models import MatchParticipant

# In add_game the player is on team 100: top 1, jungle 2, mid 3, bot 4, support 5.
MID, ALLY_TOP = 3, 1


async def mid_game(session, match_id="EUW1_1", **stats):
    await add_game(session, match_id, role="MIDDLE", **stats)
    await add_frames(session, match_id, 1, {})


async def test_a_solo_kill_has_no_assists(session):
    await mid_game(session)
    await add_event(session, "EUW1_1", "CHAMPION_KILL", 300_000, actor=MID, victim=8)
    await add_event(session, "EUW1_1", "CHAMPION_KILL", 360_000, actor=MID, victim=8, assistingParticipantIds=[2])
    await add_event(session, "EUW1_1", "CHAMPION_KILL", 1_200_000, actor=MID, victim=9, assistingParticipantIds=[])

    row = (await solo_kills(session, [ME], role="MIDDLE"))[0]

    assert (row["avg_solo_kills"], row["avg_solo_kills_before_15"]) == (2, 1)


async def test_lane_plates_are_the_enemys_in_the_players_lane_before_14(session):
    await mid_game(session)
    for ms, lane, turret_team, actor in (
        (300_000, "MID_LANE", 200, MID),  # counts, and it's the player's
        (360_000, "MID_LANE", 200, None),  # counts: a minion took it
        (1_200_000, "MID_LANE", 200, MID),  # after 14:00
        (420_000, "MID_LANE", 100, 8),  # the player's own turret
        (480_000, "TOP_LANE", 200, ALLY_TOP),  # another lane
    ):
        await add_event(session, "EUW1_1", "TURRET_PLATE_DESTROYED", ms, actor=actor, teamId=turret_team, laneType=lane)

    row = (await lane_plates(session, [ME], role="MIDDLE"))[0]

    assert (row["avg_lane_plates"], row["avg_my_plates"]) == (2, 1)


async def test_a_jungler_has_no_lane_plates(session):
    await add_game(session)
    await add_frames(session, "EUW1_1", 1, {})
    assert await lane_plates(session, [ME]) == []


async def test_damage_share_is_of_the_players_own_team(session):
    await mid_game(session, damage=3000)
    # Teammates 1 to 5 except the player deal 1,000 each; the enemy's damage doesn't count.
    await session.execute(
        update(MatchParticipant)
        .where(MatchParticipant.participant_id.in_([1, 2, 4, 5]))
        .values(damage_to_champions=1000)
    )
    await session.execute(
        update(MatchParticipant).where(MatchParticipant.participant_id > 5).values(damage_to_champions=9000)
    )
    await session.commit()

    row = (await damage_share(session, [ME], role="MIDDLE"))[0]

    assert row["avg_damage_share_pct"] == 42.9


async def test_a_roam_is_a_takedown_away_from_mid_before_14(session):
    await mid_game(session)
    await add_event(session, "EUW1_1", "CHAMPION_KILL", 300_000, actor=MID, victim=6, xy=(1000, 12000))  # top
    await add_event(
        session, "EUW1_1", "CHAMPION_KILL", 360_000, actor=2, victim=8, xy=(7000, 7000), assistingParticipantIds=[MID]
    )  # mid
    await add_event(session, "EUW1_1", "CHAMPION_KILL", 900_000, actor=MID, victim=9, xy=(13500, 1000))  # after 14:00

    row = (await roams(session, [ME], role="MIDDLE"))[0]

    assert row["avg_roam_takedowns"] == 1


# Each role's comparison


async def fill_role_cohort(session, cohort, role, participant_id):
    """30 games from 10 players in `role`, all in the sample."""
    for n in range(30):
        match_id = f"EUW1_B{n}"
        await add_game(session, match_id, role=role, puuid=f"player-{n % 10}", patch="16.21", damage=2000)
        await add_frames(session, match_id, 10, {participant_id: 3000})
        session.add(
            Sample(
                cohort=cohort,
                match_id=match_id,
                participant_id=participant_id,
                puuid=f"player-{n % 10}",
                champion_name="Viego",
                in_overall=True,
            )
        )
    await session.commit()


async def test_a_mid_comparison_uses_the_mid_measures(sessions, benchmark_sessions):  # noqa: F811
    async with benchmark_sessions() as bench, sessions() as mine:
        await fill_role_cohort(bench, "silver_middle", "MIDDLE", MID)
        await add_game(mine, "EUW1_1", role="MIDDLE", patch="16.21", damage=1500)
        await add_frames(mine, "EUW1_1", 10, {MID: 2800})

        result = await compare(mine, bench, [ME], "silver_middle")

    assert (result["status"], result["role"]) == ("ok", "MIDDLE")
    assert {r["metric"] for r in result["rows"]} >= {"damage_share", "roams", "lane_diff"}
    assert "objective_share" not in {r["metric"] for r in result["rows"]}
    roam_rows = [r for r in result["rows"] if r["metric"] == "roams"]
    assert roam_rows and all(r["context_only"] and r["clear_gap"] is None for r in roam_rows)
    assert any("Roams are context" in note for note in result["notes"])


async def test_a_supports_farm_is_context_only(sessions, benchmark_sessions):  # noqa: F811
    async with benchmark_sessions() as bench, sessions() as mine:
        await fill_role_cohort(bench, "silver_utility", "UTILITY", 5)
        await add_game(mine, "EUW1_1", role="UTILITY", patch="16.21")
        await add_frames(mine, "EUW1_1", 10, {5: 2000})

        result = await compare(mine, bench, [ME], "silver_utility")

    economy = next(t for t in result["themes"] if t["theme"] == "economy")
    assert economy["status"] == "context_only"
    assert any("support item" in note for note in result["notes"])


# A player's own numbers, when no benchmark fits


async def test_a_scope_can_keep_only_wins_or_losses(session):
    from analytics.stats import Scope, overall_cs_per_minute

    await add_game(session, "EUW1_1", role="MIDDLE", win=True, lane_cs=300)
    await add_game(session, "EUW1_2", role="MIDDLE", win=False, lane_cs=150)

    wins = await overall_cs_per_minute(session, Scope(puuids=(ME,), role="MIDDLE", win=True))
    losses = await overall_cs_per_minute(session, Scope(puuids=(ME,), role="MIDDLE", win=False))

    assert (wins[0]["avg_cs_per_min"], losses[0]["avg_cs_per_min"]) == (10, 5)


async def test_own_numbers_split_wins_and_losses_and_judge_only_10_a_side(session):
    from benchmarks.own import own_numbers

    for n in range(20):
        await add_game(session, f"EUW1_{n}", role="MIDDLE", win=n < 10, lane_cs=300 if n < 10 else 150 + n)

    result = await own_numbers(session, [ME], "MIDDLE")
    cs = next(r for r in result["rows"] if r["value"] == "avg_cs_per_min")

    assert (cs["all"]["sample"], cs["wins"]["sample"], cs["losses"]["sample"]) == (20, 10, 10)
    assert cs["wins"]["value"] == 10 and cs["clear_gap"] is True
    assert "win_rate" not in {r["metric"] for r in result["rows"]}


async def test_nine_games_a_side_gets_no_verdict(session):
    from benchmarks.own import own_numbers

    for n in range(19):
        await add_game(session, f"EUW1_{n}", role="MIDDLE", win=n < 10, lane_cs=300 if n < 10 else 150 + n)

    cs = next(r for r in (await own_numbers(session, [ME], "MIDDLE"))["rows"] if r["value"] == "avg_cs_per_min")

    assert cs["losses"]["low_sample"] is True and cs["clear_gap"] is None


async def test_own_numbers_default_to_the_main_role(sessions, test_settings):
    from fastapi.testclient import TestClient
    from test_benchmarks import gold_mid_owner

    from main import create_app

    await gold_mid_owner(sessions)
    with TestClient(create_app(test_settings)) as client:
        main_role = client.get("/own").json()
        jungle = client.get("/own", params={"role": "JUNGLE"}).json()
        wrong = client.get("/own", params={"role": "SUPPORT"})

    assert (main_role["role"], main_role["games"]) == ("MIDDLE", 12)
    assert (jungle["role"], jungle["games"]) == ("JUNGLE", 10)
    assert wrong.status_code == 422
