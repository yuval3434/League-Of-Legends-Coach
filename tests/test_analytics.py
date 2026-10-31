"""Stat functions against a real Postgres, because the maths is the SQL."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import insert

from analytics.stats import (
    after_loss_streak,
    cs_per_minute,
    deaths_by_phase,
    lane_diff,
    win_rates,
)
from ingestion.models import Match, MatchParticipant, TimelineEvent, TimelineFrame

ME = "me"
START = datetime(2026, 1, 1, tzinfo=UTC)
ROLES = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")


def _match(match_id, start, duration_s, is_remake, patch):
    return {
        "match_id": match_id,
        "platform": "EUW1",
        "queue_id": 420,
        "patch": patch,
        "game_version": f"{patch}.1.1",
        "game_start_at": start,
        "duration_s": duration_s,
        "is_remake": is_remake,
    }


def _participant(match_id, participant_id, puuid, role, win, **stats):
    return {
        "match_id": match_id,
        "participant_id": participant_id,
        "puuid": puuid,
        "team_id": 100 if participant_id <= 5 else 200,
        "team_position": role,
        "champion_id": 1,
        "champion_name": stats.pop("champion", "Viego"),
        "win": win,
        "kills": stats.pop("kills", 0),
        "deaths": stats.pop("deaths", 0),
        "assists": stats.pop("assists", 0),
        "lane_cs": stats.pop("lane_cs", 0),
        "jungle_cs": stats.pop("jungle_cs", 0),
        "gold_earned": 0,
        "damage_to_champions": 0,
        "vision_score": 0,
    }


async def add_game(
    session,
    match_id="EUW1_1",
    role="JUNGLE",
    win=True,
    start=START,
    duration_s=1800,
    is_remake=False,
    patch="16.6",
    puuid=ME,
    **stats,
):
    """Add a full 10-player game in which `puuid` is on team 100 in `role`.

    Enemies get puuids like 'enemy-JUNGLE' and teammates 'ally-TOP'.
    """
    participants = []
    for index, slot in enumerate(ROLES):
        mine = slot == role
        participants.append(
            _participant(
                match_id,
                index + 1,
                puuid if mine else f"ally-{slot}",
                slot,
                win,
                **(stats if mine else {}),
            )
        )
        participants.append(
            _participant(match_id, index + 6, f"enemy-{slot}", slot, not win)
        )
    await session.execute(
        insert(Match), [_match(match_id, start, duration_s, is_remake, patch)]
    )
    await session.execute(insert(MatchParticipant), participants)
    await session.commit()


async def add_frames(session, match_id, minute, gold, cs=None, timestamp_ms=None):
    """Add one frame. `gold` and `cs` map participant_id to a value; others get 0."""
    cs = cs or {}
    await session.execute(
        insert(TimelineFrame),
        [
            {
                "match_id": match_id,
                "participant_id": participant_id,
                "minute": minute,
                "timestamp_ms": timestamp_ms or minute * 60_000,
                "total_gold": gold.get(participant_id, 0),
                "xp": 0,
                "level": 1,
                "lane_cs": cs.get(participant_id, 0),
                "jungle_cs": 0,
                "damage_to_champions": None,
                "position_x": None,
                "position_y": None,
            }
            for participant_id in range(1, 11)
        ],
    )
    await session.commit()


async def add_deaths(session, match_id, victim_id, *timestamps_ms):
    await session.execute(
        insert(TimelineEvent),
        [
            {
                "match_id": match_id,
                "event_index": index,
                "timestamp_ms": timestamp_ms,
                "type": "CHAMPION_KILL",
                "actor_id": None,
                "victim_id": victim_id,
                "position_x": None,
                "position_y": None,
                "data": {},
            }
            for index, timestamp_ms in enumerate(timestamps_ms)
        ],
    )
    await session.commit()


def find(rows, **fields):
    matches = [r for r in rows if all(r[k] == v for k, v in fields.items())]
    assert len(matches) == 1, f"{fields}: {matches}"
    return matches[0]


@pytest.fixture
async def session(sessions):
    async with sessions() as session:
        yield session


@pytest.mark.parametrize(
    "stat", [win_rates, deaths_by_phase, lane_diff, after_loss_streak, cs_per_minute]
)
async def test_remakes_are_excluded(session, stat):
    await add_game(session, is_remake=True, deaths=1, jungle_cs=9)
    await add_frames(session, "EUW1_1", 10, {2: 500})
    assert await stat(session, [ME]) == []


@pytest.mark.parametrize(
    "stat", [win_rates, deaths_by_phase, lane_diff, after_loss_streak, cs_per_minute]
)
async def test_other_players_are_not_included(session, stat):
    await add_game(session, puuid="someone-else")
    await add_frames(session, "EUW1_1", 10, {2: 500})
    assert await stat(session, [ME]) == []


async def test_low_sample_flag_flips_at_ten_games(session):
    for n in range(9):
        await add_game(session, f"EUW1_{n}")
    assert find(await win_rates(session, [ME]), dimension="role")["low_sample"]

    await add_game(session, "EUW1_9")
    row = find(await win_rates(session, [ME]), dimension="role")
    assert row["games"] == 10
    assert row["low_sample"] is False


# Win rates


async def test_win_rates_per_champion_and_role(session):
    await add_game(session, "EUW1_1", win=True, champion="Viego")
    await add_game(session, "EUW1_2", win=False, champion="Viego")
    await add_game(session, "EUW1_3", win=False, champion="Viego")
    await add_game(session, "EUW1_4", win=True, champion="Ornn", role="TOP")

    rows = await win_rates(session, [ME])

    viego = find(rows, dimension="champion", value="Viego")
    assert (viego["games"], viego["wins"], viego["win_rate_pct"]) == (3, 1, 33.3)
    assert find(rows, dimension="role", value="TOP")["win_rate_pct"] == 100.0
    assert find(rows, dimension="role", value="JUNGLE")["games"] == 3


# Deaths by phase


async def test_deaths_land_in_the_right_phase(session):
    await add_game(session, duration_s=1800)
    await add_frames(session, "EUW1_1", 1, {})
    await add_deaths(session, "EUW1_1", 2, 899_999, 900_000, 1_499_999, 1_500_000)

    rows = await deaths_by_phase(session, [ME])

    assert [r["phase"] for r in rows] == ["early", "mid", "late"]
    assert [r["deaths"] for r in rows] == [1, 2, 1]


async def test_only_this_players_deaths_count(session):
    await add_game(session)
    await add_frames(session, "EUW1_1", 1, {})
    await add_deaths(session, "EUW1_1", 7, 60_000)

    assert find(await deaths_by_phase(session, [ME]), phase="early")["deaths"] == 0


async def test_phase_counts_only_games_that_reached_it(session):
    await add_game(session, "EUW1_1", duration_s=1000)
    await add_game(session, "EUW1_2", duration_s=1800)
    await add_frames(session, "EUW1_1", 1, {})
    await add_frames(session, "EUW1_2", 1, {})

    rows = await deaths_by_phase(session, [ME])

    assert find(rows, phase="early")["games"] == 2
    assert find(rows, phase="mid")["games"] == 2
    assert find(rows, phase="late")["games"] == 1


async def test_zero_death_games_pull_the_median_down(session):
    await add_game(session, "EUW1_1")
    await add_game(session, "EUW1_2")
    await add_game(session, "EUW1_3")
    for match_id in ("EUW1_1", "EUW1_2", "EUW1_3"):
        await add_frames(session, match_id, 1, {})
    await add_deaths(session, "EUW1_3", 2, 1000, 2000, 3000)

    row = find(await deaths_by_phase(session, [ME]), phase="early")

    assert row["avg_deaths"] == 1.0
    assert row["median_deaths"] == 0.0


async def test_deaths_per_10_minutes_uses_time_played_in_the_phase(session):
    # 5 minutes of the 'late' phase, with 2 deaths.
    await add_game(session, duration_s=1800)
    await add_frames(session, "EUW1_1", 1, {})
    await add_deaths(session, "EUW1_1", 2, 1_600_000, 1_700_000)

    assert find(await deaths_by_phase(session, [ME]), phase="late")[
        "deaths_per_10_min"
    ] == 4.0


async def test_match_without_timeline_is_not_zero_deaths(session):
    await add_game(session)
    assert await deaths_by_phase(session, [ME]) == []


# Lane difference. Participants: 1-5 are team 100, 6-10 team 200, and both run
# TOP, JUNGLE, MIDDLE, BOTTOM, UTILITY. So 2 and 7 are the two junglers.


async def test_opponent_is_same_role_on_other_team(session):
    await add_game(session)
    await add_frames(
        session,
        "EUW1_1",
        10,
        gold={2: 3000, 7: 2500, 1: 9000, 6: 9000},
        cs={2: 50, 7: 60},
    )

    row = find(await lane_diff(session, [ME]), minute=10, result="all")

    assert row["role"] == "JUNGLE"
    assert row["avg_gold_diff"] == 500
    assert row["avg_cs_diff"] == -10


async def test_cs_diff_includes_jungle_camps(session):
    await add_game(session)
    await add_frames(session, "EUW1_1", 10, {})
    await session.execute(
        TimelineFrame.__table__.update()
        .where(TimelineFrame.participant_id == 2)
        .values(lane_cs=5, jungle_cs=40)
    )
    await session.commit()

    row = find(await lane_diff(session, [ME]), minute=10, result="all")

    assert row["avg_cs_diff"] == 45


async def test_median_ignores_one_stomp(session):
    for n, gold in enumerate((100, 200, 9000)):
        await add_game(session, f"EUW1_{n}")
        await add_frames(session, f"EUW1_{n}", 10, {2: gold})

    row = find(await lane_diff(session, [ME]), minute=10, result="all")

    assert row["avg_gold_diff"] == 3100
    assert row["median_gold_diff"] == 200


async def test_jungle_splits_by_result(session):
    await add_game(session, "EUW1_1", win=True)
    await add_game(session, "EUW1_2", win=False)
    await add_frames(session, "EUW1_1", 10, {2: 800})
    await add_frames(session, "EUW1_2", 10, {7: 300})

    rows = await lane_diff(session, [ME])

    assert find(rows, minute=10, result="win")["avg_gold_diff"] == 800
    assert find(rows, minute=10, result="loss")["avg_gold_diff"] == -300
    assert find(rows, minute=10, result="all")["games"] == 2


async def test_other_roles_have_no_win_loss_split(session):
    await add_game(session, role="TOP")
    await add_frames(session, "EUW1_1", 10, {1: 100})

    rows = await lane_diff(session, [ME])

    assert [r["result"] for r in rows] == ["all"]


async def test_final_frame_of_a_short_game_is_not_a_checkpoint(session):
    # Ends at 14:50, so its last frame is numbered 15 but isn't minute 15.
    await add_game(session, duration_s=890)
    await add_frames(session, "EUW1_1", 15, {2: 900}, timestamp_ms=890_000)

    assert await lane_diff(session, [ME]) == []


async def test_several_players_are_pooled(session):
    await add_game(session, "EUW1_1", puuid="a")
    await add_game(session, "EUW1_2", puuid="b")
    await add_frames(session, "EUW1_1", 10, {2: 100})
    await add_frames(session, "EUW1_2", 10, {2: 300})

    row = find(await lane_diff(session, ["a", "b"]), minute=10, result="all")

    assert row["games"] == 2
    assert row["avg_gold_diff"] == 200


# Loss streaks


async def add_series(session, results, gap=timedelta(minutes=45)):
    """Add games in order; `results` is like 'WLLW'."""
    for n, result in enumerate(results):
        await add_game(
            session,
            f"EUW1_{n}",
            win=result == "W",
            start=START + n * gap,
            duration_s=1800,
        )


async def test_games_are_grouped_by_losses_before(session):
    await add_series(session, "WLLW")

    rows = await after_loss_streak(session, [ME])

    assert [(r["losses_before"], r["games"]) for r in rows] == [
        ("0", 2),  # the first game, and the first loss after a win
        ("1", 1),
        ("2", 1),
    ]
    assert find(rows, losses_before="2")["win_rate_pct"] == 100.0


async def test_long_streaks_share_the_top_bucket(session):
    await add_series(session, "LLLLLW")

    rows = await after_loss_streak(session, [ME])

    top = find(rows, losses_before="3+")
    assert (top["games"], top["wins"]) == (3, 1)


async def test_long_break_resets_the_streak(session):
    await add_series(session, "LL", gap=timedelta(hours=7))

    rows = await after_loss_streak(session, [ME])

    assert [(r["losses_before"], r["games"]) for r in rows] == [("0", 2)]


async def test_break_is_measured_from_the_end_of_the_previous_game(session):
    # Starts are 6h15m apart, but only 5h45m pass after the 30-minute game.
    await add_series(session, "LL", gap=timedelta(hours=6, minutes=15))

    rows = await after_loss_streak(session, [ME])

    assert [r["losses_before"] for r in rows] == ["0", "1"]


async def test_streaks_are_tracked_per_player(session):
    await add_game(session, "EUW1_1", puuid="a", win=False, start=START)
    await add_game(
        session,
        "EUW1_2",
        puuid="b",
        win=False,
        start=START + timedelta(minutes=45),
    )

    rows = await after_loss_streak(session, ["a", "b"])

    assert [(r["losses_before"], r["games"]) for r in rows] == [("0", 2)]


async def test_kda_treats_zero_deaths_as_one(session):
    await add_game(session, kills=3, assists=4, deaths=0)

    row = find(await after_loss_streak(session, [ME]), losses_before="0")

    assert row["avg_kda"] == 7.0


# CS per minute


async def test_cs_per_minute_counts_lane_and_jungle(session):
    await add_game(session, duration_s=1800, lane_cs=60, jungle_cs=90)

    row = find(await cs_per_minute(session, [ME]), patch="16.6")

    assert row["avg_cs_per_min"] == 5.0


async def test_patches_sort_numerically(session):
    await add_game(session, "EUW1_1", patch="16.10")
    await add_game(session, "EUW1_2", patch="16.6")
    await add_game(session, "EUW1_3", patch="15.24")

    rows = await cs_per_minute(session, [ME])

    assert [r["patch"] for r in rows] == ["15.24", "16.6", "16.10"]


async def test_roles_are_kept_apart(session):
    await add_game(session, "EUW1_1", role="JUNGLE")
    await add_game(session, "EUW1_2", role="UTILITY")

    rows = await cs_per_minute(session, [ME])

    assert {r["role"] for r in rows} == {"JUNGLE", "UTILITY"}
