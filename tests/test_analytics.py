"""Stat functions against a real Postgres, because the maths is the SQL."""

from datetime import UTC, datetime, timedelta
from itertools import count

import pytest
from sqlalchemy import insert

from analytics.jungle import (
    deaths_before_objective,
    first_lane_kill,
    kill_participation,
    objective_control,
    wards_per_minute,
)
from analytics.stats import (
    after_loss_streak,
    cs_per_minute,
    deaths_by_phase,
    lane_diff,
    win_rate_by_gold_diff,
    win_rates,
)
from ingestion.models import Match, MatchParticipant, TimelineEvent, TimelineFrame

ME = "me"
START = datetime(2026, 1, 1, tzinfo=UTC)
ROLES = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")
ALL_STATS = [
    win_rates,
    deaths_by_phase,
    lane_diff,
    after_loss_streak,
    cs_per_minute,
    objective_control,
    deaths_before_objective,
    kill_participation,
    wards_per_minute,
    first_lane_kill,
]
_event_ids = count(1000)


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


async def add_event(session, match_id, kind, ms, actor=None, victim=None, xy=None, **data):
    x, y = xy or (None, None)
    await session.execute(
        insert(TimelineEvent),
        [
            {
                "match_id": match_id,
                "event_index": next(_event_ids),
                "timestamp_ms": ms,
                "type": kind,
                "actor_id": actor,
                "victim_id": victim,
                "position_x": x,
                "position_y": y,
                "data": data,
            }
        ],
    )
    await session.commit()


async def add_objective(session, match_id, ms, monster, team, actor=None, subtype=None):
    data = {"monsterType": monster, "killerTeamId": team}
    if subtype:
        data["monsterSubType"] = subtype
    await add_event(session, match_id, "ELITE_MONSTER_KILL", ms, actor=actor, **data)


def find(rows, **fields):
    matches = [r for r in rows if all(r[k] == v for k, v in fields.items())]
    assert len(matches) == 1, f"{fields}: {matches}"
    return matches[0]


@pytest.fixture
async def session(sessions):
    async with sessions() as session:
        yield session


@pytest.mark.parametrize(
    "stat", ALL_STATS
)
async def test_remakes_are_excluded(session, stat):
    await add_game(session, is_remake=True, deaths=1, jungle_cs=9)
    await add_frames(session, "EUW1_1", 10, {2: 500})
    assert await stat(session, [ME]) == []


@pytest.mark.parametrize(
    "stat", ALL_STATS
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


# Win rate by gold difference at minute 10


@pytest.mark.parametrize(
    ("gold_diff", "bucket"),
    [
        (-501, "behind 500+"),
        (-500, "behind 0-500"),
        (-1, "behind 0-500"),
        (0, "ahead 0-500"),
        (499, "ahead 0-500"),
        (500, "ahead 500+"),
    ],
)
async def test_gold_diff_bucket_edges(session, gold_diff, bucket):
    await add_game(session)
    await add_frames(session, "EUW1_1", 10, {2: 1000 + gold_diff, 7: 1000})

    rows = await win_rate_by_gold_diff(session, [ME])

    assert find(rows, bucket=bucket)["games"] == 1
    assert sum(r["games"] for r in rows) == 1


async def test_buckets_report_win_rate_and_keep_empty_ones(session):
    await add_game(session, "EUW1_1", win=True)
    await add_game(session, "EUW1_2", win=False)
    await add_game(session, "EUW1_3", win=False)
    for match_id in ("EUW1_1", "EUW1_2", "EUW1_3"):
        await add_frames(session, match_id, 10, {2: 900})

    rows = await win_rate_by_gold_diff(session, [ME])

    assert [r["bucket"] for r in rows] == [
        "behind 500+",
        "behind 0-500",
        "ahead 0-500",
        "ahead 500+",
    ]
    ahead = find(rows, bucket="ahead 500+")
    assert (ahead["games"], ahead["wins"], ahead["win_rate_pct"]) == (3, 1, 33.3)
    empty = find(rows, bucket="behind 500+")
    assert (empty["games"], empty["win_rate_pct"]) == (0, None)
    assert empty["low_sample"] is True


async def test_gold_buckets_ignore_other_roles_and_remakes(session):
    await add_game(session, "EUW1_1", role="TOP")
    await add_game(session, "EUW1_2", is_remake=True)
    await add_frames(session, "EUW1_1", 10, {1: 900})
    await add_frames(session, "EUW1_2", 10, {2: 900})

    rows = await win_rate_by_gold_diff(session, [ME])

    assert sum(r["games"] for r in rows) == 0


async def test_gold_buckets_skip_games_shorter_than_ten_minutes(session):
    await add_game(session, duration_s=590)
    await add_frames(session, "EUW1_1", 10, {2: 900}, timestamp_ms=590_000)

    rows = await win_rate_by_gold_diff(session, [ME])

    assert sum(r["games"] for r in rows) == 0


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


# Jungle stats. In add_game the player is participant 2 on team 100, with
# teammates 1, 3, 4, 5. The enemies are 6 TOP, 7 JUNGLE, 8 MIDDLE, 9 BOTTOM and
# 10 UTILITY.


async def jungle_game(session, match_id="EUW1_1", **kwargs):
    await add_game(session, match_id, **kwargs)
    await add_frames(session, match_id, 1, {})


@pytest.mark.parametrize(
    "stat",
    [
        objective_control,
        deaths_before_objective,
        kill_participation,
        wards_per_minute,
        first_lane_kill,
    ],
)
async def test_jungle_stats_ignore_other_roles(session, stat):
    await jungle_game(session, role="TOP")
    await add_objective(session, "EUW1_1", 60_000, "DRAGON", 100)
    assert await stat(session, [ME]) == []


async def test_objectives_split_by_team(session):
    await jungle_game(session)
    await add_objective(session, "EUW1_1", 1000, "DRAGON", 100, actor=2)
    await add_objective(session, "EUW1_1", 2000, "DRAGON", 100, actor=3)
    await add_objective(session, "EUW1_1", 3000, "DRAGON", 200, actor=7)

    row = find(await objective_control(session, [ME]), objective="DRAGON")

    assert (row["team_taken"], row["enemy_taken"]) == (2, 1)
    assert row["team_share_pct"] == 66.7
    assert row["my_last_hits"] == 1


async def test_team_is_relative_to_the_player(session):
    await jungle_game(session, "EUW1_1")
    await session.execute(
        MatchParticipant.__table__.update()
        .where(MatchParticipant.puuid == ME)
        .values(team_id=200)
    )
    await session.commit()
    await add_objective(session, "EUW1_1", 1000, "DRAGON", 200)

    row = find(await objective_control(session, [ME]), objective="DRAGON")

    assert (row["team_taken"], row["enemy_taken"]) == (1, 0)


async def test_neutral_objective_kills_count_for_neither_team(session):
    await jungle_game(session)
    await add_objective(session, "EUW1_1", 1000, "RIFTHERALD", 300)
    await add_objective(session, "EUW1_1", 2000, "DRAGON", 100)

    rows = await objective_control(session, [ME])

    assert [r["objective"] for r in rows] == ["DRAGON"]


async def test_elder_is_separate_from_dragons(session):
    await jungle_game(session)
    await add_objective(session, "EUW1_1", 1000, "DRAGON", 100, subtype="FIRE_DRAGON")
    await add_objective(session, "EUW1_1", 2000, "DRAGON", 200, subtype="ELDER_DRAGON")

    rows = await objective_control(session, [ME])

    assert find(rows, objective="DRAGON")["team_taken"] == 1
    assert find(rows, objective="ELDER_DRAGON")["enemy_taken"] == 1


async def test_unknown_objectives_get_their_own_row(session):
    await jungle_game(session)
    await add_objective(session, "EUW1_1", 1000, "VOID_GATOR", 100)

    rows = await objective_control(session, [ME])

    assert find(rows, objective="VOID_GATOR")["team_taken"] == 1


async def test_games_without_an_objective_count_as_zero(session):
    await jungle_game(session, "EUW1_1")
    await jungle_game(session, "EUW1_2")
    await jungle_game(session, "EUW1_3")
    await add_objective(session, "EUW1_1", 1000, "BARON_NASHOR", 100)

    row = find(await objective_control(session, [ME]), objective="BARON_NASHOR")

    assert row["games"] == 3
    assert row["avg_team_taken"] == 0.33
    assert row["median_team_taken"] == 0.0


async def death(session, match_id, victim, ms):
    await add_event(session, match_id, "CHAMPION_KILL", ms, actor=7, victim=victim)


async def test_deaths_are_counted_in_the_60_seconds_before(session):
    await jungle_game(session)
    await add_objective(session, "EUW1_1", 600_000, "DRAGON", 200)
    await death(session, "EUW1_1", 2, 540_000)  # exactly 60s before

    row = find(
        await deaths_before_objective(session, [ME]),
        objective="DRAGON",
        taken_by="enemy",
    )

    assert (row["objectives"], row["my_death_pct"], row["team_death_pct"]) == (
        1,
        100.0,
        100.0,
    )


async def test_deaths_outside_the_window_do_not_count(session):
    await jungle_game(session)
    await add_objective(session, "EUW1_1", 600_000, "DRAGON", 200)
    await death(session, "EUW1_1", 2, 539_999)
    await death(session, "EUW1_1", 2, 600_001)

    row = find(await deaths_before_objective(session, [ME]), objective="DRAGON")

    assert row["my_death_pct"] == 0.0


async def test_teammate_deaths_have_their_own_column(session):
    await jungle_game(session)
    await add_objective(session, "EUW1_1", 600_000, "DRAGON", 200)
    await death(session, "EUW1_1", 3, 590_000)
    await death(session, "EUW1_1", 4, 595_000)

    row = find(await deaths_before_objective(session, [ME]), objective="DRAGON")

    assert row["my_death_pct"] == 0.0
    assert row["team_death_pct"] == 100.0
    assert row["avg_team_deaths"] == 2.0


async def test_enemy_deaths_are_not_team_deaths(session):
    await jungle_game(session)
    await add_objective(session, "EUW1_1", 600_000, "DRAGON", 100)
    await death(session, "EUW1_1", 8, 590_000)

    row = find(await deaths_before_objective(session, [ME]), objective="DRAGON")

    assert row["team_death_pct"] == 0.0


async def test_baseline_comes_back_on_every_row(session):
    await add_game(session)
    for minute in range(4, 8):  # minutes 5, 6 and 7 are windows; 4 is too early
        await add_frames(session, "EUW1_1", minute, {})
    await add_objective(session, "EUW1_1", 400_000, "DRAGON", 100)
    await add_objective(session, "EUW1_1", 410_000, "BARON_NASHOR", 200)
    await death(session, "EUW1_1", 2, 290_000)  # inside only the minute 5 window
    await death(session, "EUW1_1", 3, 415_000)  # inside only the minute 7 window

    rows = await deaths_before_objective(session, [ME])

    assert len(rows) == 2
    for row in rows:
        assert row["baseline_windows"] == 3
        assert row["baseline_my_death_pct"] == 33.3
        assert row["baseline_team_death_pct"] == 66.7


async def test_baseline_is_empty_without_frames_after_minute_5(session):
    await jungle_game(session)  # its only frame is minute 1
    await add_objective(session, "EUW1_1", 200_000, "HORDE", 100)

    row = (await deaths_before_objective(session, [ME]))[0]

    assert (row["baseline_windows"], row["baseline_my_death_pct"]) == (0, None)


async def test_kill_participation_uses_the_whole_teams_kills(session):
    await add_game(session, kills=2, assists=2)
    await add_frames(session, "EUW1_1", 1, {})
    await session.execute(
        MatchParticipant.__table__.update()
        .where(MatchParticipant.participant_id == 1)
        .values(kills=6)
    )
    await session.execute(
        MatchParticipant.__table__.update()
        .where(MatchParticipant.participant_id == 7)
        .values(kills=50)
    )
    await session.commit()

    row = (await kill_participation(session, [ME]))[0]

    assert row["avg_kill_participation_pct"] == 50.0


async def test_kill_participation_skips_games_with_no_team_kills(session):
    await jungle_game(session)
    assert await kill_participation(session, [ME]) == []


async def test_wards_per_minute_uses_game_length(session):
    await jungle_game(session, duration_s=600)
    for ms in (1000, 2000):
        await add_event(
            session, "EUW1_1", "WARD_PLACED", ms, actor=2, wardType="SIGHT_WARD"
        )
    await add_event(
        session, "EUW1_1", "WARD_KILL", 3000, actor=2, wardType="CONTROL_WARD"
    )

    row = (await wards_per_minute(session, [ME]))[0]

    assert (row["placed"], row["destroyed"]) == (2, 1)
    assert row["avg_placed_per_min"] == 0.2
    assert row["avg_destroyed_per_min"] == 0.1


@pytest.mark.parametrize("ward", ["UNDEFINED", "TEEMO_MUSHROOM"])
@pytest.mark.parametrize("kind", ["WARD_PLACED", "WARD_KILL"])
async def test_wards_filter_out_non_wards(session, ward, kind):
    await jungle_game(session)
    await add_event(session, "EUW1_1", kind, 1000, actor=2, wardType=ward)

    row = (await wards_per_minute(session, [ME]))[0]

    assert (row["placed"], row["destroyed"]) == (0, 0)


async def test_other_players_wards_do_not_count(session):
    await jungle_game(session)
    await add_event(
        session, "EUW1_1", "WARD_PLACED", 1000, actor=3, wardType="SIGHT_WARD"
    )

    assert (await wards_per_minute(session, [ME]))[0]["placed"] == 0


async def test_games_with_no_wards_count_as_zero(session):
    await jungle_game(session, "EUW1_1", duration_s=600)
    await jungle_game(session, "EUW1_2", duration_s=600)
    await add_event(
        session, "EUW1_1", "WARD_PLACED", 1000, actor=2, wardType="SIGHT_WARD"
    )

    row = (await wards_per_minute(session, [ME]))[0]

    assert row["games"] == 2
    assert row["avg_placed_per_min"] == 0.05


# Real positions: turrets from Riot's events, which carry the lane.
@pytest.mark.parametrize(
    ("victim", "role", "xy", "lane"),
    [
        (6, "TOP", (981, 10441), "top"),
        (6, "TOP", (4318, 13875), "top"),
        (6, "TOP", (7943, 13411), "top"),
        (8, "MIDDLE", (5846, 6396), "mid"),
        (8, "MIDDLE", (8955, 8510), "mid"),
        (9, "BOTTOM", (10504, 1029), "bot"),
        (9, "BOTTOM", (13866, 4505), "bot"),
        (10, "UTILITY", (6919, 1483), "bot"),
    ],
)
async def test_first_lane_kill_reads_the_lane(session, victim, role, xy, lane):
    await jungle_game(session)
    await add_event(
        session, "EUW1_1", "CHAMPION_KILL", 300_000, actor=2, victim=victim, xy=xy
    )

    rows = await first_lane_kill(session, [ME])

    row = find(rows, lane=lane, victim_role=role)
    assert (row["games"], row["avg_minute"], row["games_before_10"]) == (1, 5.0, 1)


async def test_an_assist_counts_as_a_lane_kill(session):
    await jungle_game(session)
    await add_event(
        session,
        "EUW1_1",
        "CHAMPION_KILL",
        300_000,
        actor=1,
        victim=6,
        xy=(981, 10441),
        assistingParticipantIds=[2],
    )

    assert find(await first_lane_kill(session, [ME]), lane="top")["games"] == 1


async def test_only_the_first_lane_kill_counts(session):
    await jungle_game(session)
    await add_event(
        session, "EUW1_1", "CHAMPION_KILL", 500_000, actor=2, victim=8, xy=(5846, 6396)
    )
    await add_event(
        session, "EUW1_1", "CHAMPION_KILL", 300_000, actor=2, victim=6, xy=(981, 10441)
    )

    rows = await first_lane_kill(session, [ME])

    assert [r["lane"] for r in rows] == ["top"]


@pytest.mark.parametrize(
    ("actor", "victim", "xy", "ms"),
    [
        (2, 7, (981, 10441), 300_000),  # enemy jungler, not a laner
        (2, 6, (5846, 6396), 300_000),  # enemy top laner, roaming mid
        (2, 6, (3000, 7000), 300_000),  # enemy top laner, in the jungle
        (2, 6, (1000, 1000), 300_000),  # enemy top laner, in their base
        (3, 6, (981, 10441), 300_000),  # a teammate's kill, no assist
        (7, 2, (981, 10441), 300_000),  # the player's own death
        (2, 1, (981, 10441), 300_000),  # the allied top laner, in top lane
        (2, 6, (981, 10441), 900_000),  # too late
    ],
)
async def test_what_is_not_a_lane_kill(session, actor, victim, xy, ms):
    await jungle_game(session)
    await add_event(
        session, "EUW1_1", "CHAMPION_KILL", ms, actor=actor, victim=victim, xy=xy
    )

    rows = await first_lane_kill(session, [ME])

    assert [(r["lane"], r["games"], r["avg_minute"]) for r in rows] == [
        ("none", 1, None)
    ]


async def test_first_lane_kill_shares_add_up(session):
    await jungle_game(session, "EUW1_1")
    await jungle_game(session, "EUW1_2")
    await add_event(
        session, "EUW1_1", "CHAMPION_KILL", 700_000, actor=2, victim=6, xy=(981, 10441)
    )

    rows = await first_lane_kill(session, [ME])

    top, none = find(rows, lane="top"), find(rows, lane="none")
    assert (top["share_pct"], top["total_games"], top["games_before_10"]) == (50.0, 2, 0)
    assert (none["share_pct"], none["total_games"]) == (50.0, 2)
