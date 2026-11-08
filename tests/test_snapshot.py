"""A benchmark kept as aggregates only: what the demo ships instead of other players' games."""

import json
from pathlib import Path

import pytest
from sqlalchemy import delete
from test_analytics import add_frames, add_game
from test_benchmarks import ME, SILVER, add_sampled_game, benchmark_sessions  # noqa: F401

from benchmarks.compare import cohort_sizes, compare, coverage
from benchmarks.models import Sample
from benchmarks.snapshot import build, identifying_keys, save

SHIPPED = Path(__file__).parent.parent / "demo" / "benchmark.json"


async def add_benchmark_and_me(bench, mine):
    for n in range(30):
        await add_sampled_game(
            bench, f"EUW1_{n}", f"player-{n % 10}", patch="16.21", gold=1000 + 50 * (n % 3)
        )
    for n in range(12):
        await add_game(mine, f"EUW1_9{n}", patch="16.21")
        await add_frames(mine, f"EUW1_9{n}", 10, {2: 900 + n})


async def test_a_snapshot_gives_the_same_comparison_as_the_games_it_came_from(
    sessions, benchmark_sessions  # noqa: F811
):
    async with benchmark_sessions() as bench, sessions() as mine:
        await add_benchmark_and_me(bench, mine)
        from_games = await compare(mine, bench, [ME], SILVER)
        kept = await build(bench, SILVER)
        # The games go; only the snapshot is left.
        await bench.execute(delete(Sample))
        await bench.commit()
        assert (await compare(mine, bench, [ME], SILVER))["status"] == "no_benchmark"
        await save(bench, [kept])
        from_snapshot = await compare(mine, bench, [ME], SILVER)

    assert from_games["status"] == from_snapshot["status"] == "ok"
    assert from_snapshot["benchmark_games"] == 30
    assert from_snapshot["benchmark_players"] == 10
    assert from_snapshot["rows"] == from_games["rows"]
    assert from_snapshot["themes"] == from_games["themes"]


async def test_a_snapshot_cohort_is_offered_with_its_size(sessions, benchmark_sessions):  # noqa: F811
    async with benchmark_sessions() as bench, sessions() as mine:
        await add_benchmark_and_me(bench, mine)
        kept = await build(bench, SILVER)
        await bench.execute(delete(Sample))
        await save(bench, [kept])
        sizes = await cohort_sizes(bench)
        covered = await coverage(mine, bench, [ME])

    assert sizes[SILVER] == {"cohort": SILVER, "checked": 0, "games": 30, "players": 10}
    [row] = [b for b in covered["benchmarks"] if b["cohort"] == SILVER]
    assert (row["champion"], row["games"], row["has_benchmark"]) == (None, 30, True)


async def test_a_cohort_with_games_ignores_any_snapshot(sessions, benchmark_sessions):  # noqa: F811
    async with benchmark_sessions() as bench, sessions() as mine:
        await add_benchmark_and_me(bench, mine)
        kept = await build(bench, SILVER)
        kept["size"] = {"games": 999, "players": 999, "patches": ["16.21"]}
        await save(bench, [kept])
        result = await compare(mine, bench, [ME], SILVER)
        sizes = await cohort_sizes(bench)

    assert result["benchmark_games"] == sizes[SILVER]["games"] == 30


def test_a_snapshot_with_an_id_in_it_is_refused():
    assert identifying_keys({"metrics": {"x": [{"puuid": "abc", "games": 3}]}}) == ["puuid"]
    assert identifying_keys({"rows": [{"match_id": "EUW1_1"}]}) == ["match_id"]


@pytest.mark.parametrize("snapshot", json.loads(SHIPPED.read_text(encoding="utf-8"))["snapshots"])
def test_the_shipped_snapshot_holds_only_cohort_aggregates(snapshot):
    assert identifying_keys(snapshot) == []
    assert snapshot["size"]["games"] >= 30
    # Every row rests on many games, never one player's game or a champion's handful.
    for name, rows in snapshot["metrics"].items():
        for row in rows:
            assert row.get("games", 0) >= 30, (name, row)
    assert [r["dimension"] for r in snapshot["metrics"]["win_rate"]] == ["role"]
