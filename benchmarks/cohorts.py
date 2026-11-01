"""The benchmark cohorts and the sample sizes they must reach."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Cohort:
    tier: str
    # Peers share the player's opponent level, so stats measured against the
    # opponent mean the same on both sides. Higher tiers get absolute stats only.
    relative_stats: bool


COHORTS = {
    "silver": Cohort(tier="SILVER", relative_stats=True),
    "emerald": Cohort(tier="EMERALD", relative_stats=False),
}

WINDOW_DAYS = 28
TARGET_OVERALL = 500
TARGET_PER_CHAMPION = 100
MAX_GAMES_PER_PLAYER_CHAMPION = 10

# Below either floor, there is no benchmark. It is never replaced by anything else.
MIN_BENCHMARK_GAMES = 30
MIN_BENCHMARK_PLAYERS = 10

# A champion needs this many jungle games from the tracked player to be a target.
MIN_TARGET_CHAMPION_GAMES = 5
