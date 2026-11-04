"""Gold and CS by stretch: lost to the enemy jungler, and against each cohort."""

from fastapi.testclient import TestClient
from test_analytics import ME, add_frames, add_game, session  # noqa: F401
from test_benchmarks import SILVER, add_sampled_game, benchmark_sessions, fill_cohort  # noqa: F401
from test_players import FRIEND, two_players

from analytics.jungle import farm_gained_by_stretch, farm_vs_jungler_by_stretch
from benchmarks.stretches import farm_by_stretch
from main import create_app

# In add_game the player is the jungler, participant 2, and the enemy jungler is 7.
MINE, THEIRS = 2, 7


def by_stretch(rows):
    return {row["stretch"]: row for row in rows}


async def add_stretch_game(session, match_id, gold, cs=None, duration_s=1800, patch="16.6"):
    """`gold` and `cs` map a minute to (mine, enemy jungler's)."""
    await add_game(session, match_id, duration_s=duration_s, patch=patch)
    for minute, (mine, theirs) in gold.items():
        mine_cs, theirs_cs = (cs or {}).get(minute, (0, 0))
        await add_frames(
            session, match_id, minute, {MINE: mine, THEIRS: theirs}, {MINE: mine_cs, THEIRS: theirs_cs}
        )


async def test_a_stretch_is_what_was_gained_between_its_two_minutes(session):
    await add_stretch_game(
        session,
        "EUW1_1",
        gold={0: (500, 500), 10: (3500, 3800), 15: (5500, 5600), 20: (7600, 8100)},
        cs={0: (0, 0), 10: (60, 66), 15: (90, 95), 20: (118, 124)},
    )

    gained = by_stretch(await farm_gained_by_stretch(session, [ME]))
    lost = by_stretch(await farm_vs_jungler_by_stretch(session, [ME]))

    assert [gained[s]["avg_gold_gained"] for s in ("0-10", "10-15", "15-20")] == [3000, 2000, 2100]
    assert [gained[s]["avg_cs_gained"] for s in ("0-10", "10-15", "15-20")] == [60, 30, 28]
    # The enemy gained 3300, 1800 and 2500: lost 300, won back 200, lost 400.
    assert [lost[s]["avg_gold_diff"] for s in ("0-10", "10-15", "15-20")] == [-300, 200, -400]
    assert [lost[s]["avg_cs_diff"] for s in ("0-10", "10-15", "15-20")] == [-6, 1, -1]


async def test_a_game_counts_only_in_stretches_it_lasted_through(session):
    full = {0: (500, 500), 10: (3500, 3500), 15: (5500, 5500), 20: (7500, 7500)}
    await add_stretch_game(session, "EUW1_1", full)
    # Ends at 17:00, so it has a frame numbered 20 that isn't minute 20.
    await add_stretch_game(session, "EUW1_2", full, duration_s=1020)

    games = {s: row["games"] for s, row in by_stretch(await farm_gained_by_stretch(session, [ME])).items()}

    assert games == {"0-10": 2, "10-15": 2, "15-20": 1}


async def test_every_stretch_has_its_sample_and_margin(session):
    for n, enemy in enumerate((3600, 3700, 3800)):
        await add_stretch_game(session, f"EUW1_{n}", {0: (500, 500), 10: (3500, enemy)})

    row = by_stretch(await farm_vs_jungler_by_stretch(session, [ME]))["0-10"]

    assert (row["games"], row["low_sample"]) == (3, True)
    assert row["avg_gold_diff"] == -200
    # Spread 100 over 3 games: 1.96 * 100 / sqrt(3).
    assert row["margin_gold_diff"] == 113
    assert row["clear_gold_diff"] is True


async def test_a_loss_inside_the_margin_is_not_clear(session):
    for n, enemy in enumerate((3000, 4000)):
        await add_stretch_game(session, f"EUW1_{n}", {0: (500, 500), 10: (3400, enemy)})

    row = by_stretch(await farm_vs_jungler_by_stretch(session, [ME]))["0-10"]

    assert row["avg_gold_diff"] == -100
    assert row["clear_gold_diff"] is False


async def test_a_cohort_comparison_has_both_samples_and_no_theme(sessions, benchmark_sessions):  # noqa: F811
    async with benchmark_sessions() as bench, sessions() as mine:
        for n in range(30):
            await add_sampled_game(bench, f"EUW1_{n}", f"player-{n % 10}", patch="16.21")
            # add_sampled_game sets minute 10; add the start for 0-10.
            await add_frames(bench, f"EUW1_{n}", 0, {MINE: 500})
        await add_stretch_game(mine, "EUW1_1", {0: (500, 500), 10: (900, 1000)}, patch="16.21")

        result = await farm_by_stretch(mine, bench, [ME], {SILVER: None, "emerald": None})

    silver = result["benchmarks"][SILVER]
    assert silver["status"] == "ok"
    row = next(r for r in silver["rows"] if r["stretch"] == "0-10" and r["value"] == "avg_gold_gained")
    assert (row["my_value"], row["my_sample"], row["my_low_sample"]) == (400, 1, True)
    assert (row["benchmark_value"], row["benchmark_sample"]) == (500, 30)
    assert row["difference"] == -100
    # Never part of a theme, so it can never become a finding.
    assert "theme" not in row
    assert result["benchmarks"]["emerald"]["status"] == "no_benchmark"
    assert result["vs_enemy_jungler"][0]["avg_gold_diff"] == -100


async def test_a_cohort_that_doesnt_fit_the_player_has_no_substitute(sessions, benchmark_sessions):  # noqa: F811
    async with benchmark_sessions() as bench, sessions() as mine:
        for n in range(30):
            await add_sampled_game(bench, f"EUW1_{n}", f"player-{n % 10}", patch="16.21")

        result = await farm_by_stretch(mine, bench, [ME], {SILVER: "They're ranked Gold.", "emerald": None})

    silver = result["benchmarks"][SILVER]
    assert (silver["status"], silver["rows"]) == ("no_benchmark", [])
    assert "ranked Gold" in silver["note"]


async def test_the_endpoint_follows_the_player_asked_for(test_settings, sessions, benchmark_sessions):  # noqa: F811
    await two_players(sessions, friend_tier="SILVER", friend_role="MIDDLE")
    async with benchmark_sessions() as bench:
        await fill_cohort(bench)
    with TestClient(create_app(test_settings)) as client:
        friend = client.get("/benchmarks/stretches", params={"player": FRIEND})
        mine = client.get("/benchmarks/stretches").json()

    # A mid laner gets no jungle benchmark; the owner's own stays.
    assert friend.json()["benchmarks"][SILVER]["status"] == "no_benchmark"
    assert mine["benchmarks"][SILVER]["status"] == "ok"
    assert "puuid" not in friend.text.lower()
