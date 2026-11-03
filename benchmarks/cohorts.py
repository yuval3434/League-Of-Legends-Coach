"""The benchmark cohorts and the sample sizes they must reach."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Cohort:
    tier: str
    # Peers share the player's opponent level, so stats measured against the
    # opponent mean the same on both sides. Higher tiers get absolute stats only.
    relative_stats: bool
    # "peers" is for players of this tier; "target" is for players below it.
    audience: str


COHORTS = {
    "silver": Cohort(tier="SILVER", relative_stats=True, audience="peers"),
    "emerald": Cohort(tier="EMERALD", relative_stats=False, audience="target"),
}

TIERS = (
    "IRON",
    "BRONZE",
    "SILVER",
    "GOLD",
    "PLATINUM",
    "EMERALD",
    "DIAMOND",
    "MASTER",
    "GRANDMASTER",
    "CHALLENGER",
)
# Every cohort is made of junglers.
BENCHMARK_ROLE = "JUNGLE"


def why_no_benchmark(
    cohort: str, rank_tier: str | None, main_role: str | None, rank_checked: bool = True
) -> str | None:
    """Why a player can't be compared with `cohort`, or None if they can.

    A cohort is never swapped for another one: a player it doesn't fit gets no
    benchmark at all.
    """
    group = COHORTS[cohort]
    name = group.tier.capitalize()
    if main_role is None:
        return "This player has no ranked games, so there's nothing to compare."
    if main_role != BENCHMARK_ROLE:
        role = {"MIDDLE": "mid", "BOTTOM": "bot", "UTILITY": "support"}.get(
            main_role, main_role.lower()
        )
        return f"The benchmarks are junglers, and this player mostly plays {role}."
    if not rank_checked:
        return "This player's rank hasn't been checked yet: sync them again."
    if rank_tier is None:
        return "This player is unranked in solo/duo, so no rank's benchmark fits."
    rank = rank_tier.capitalize()
    if group.audience == "peers" and rank_tier != group.tier:
        return f"The {name} benchmark is for {name} players, and this player is {rank}."
    if group.audience == "target" and TIERS.index(rank_tier) >= TIERS.index(group.tier):
        return f"{name} is a target for players ranked below it, and this player is {rank}."
    return None

WINDOW_DAYS = 28
TARGET_OVERALL = 500
TARGET_PER_CHAMPION = 100
MAX_GAMES_PER_PLAYER_CHAMPION = 10

# Below either floor, there is no benchmark. It is never replaced by anything else.
MIN_BENCHMARK_GAMES = 30
MIN_BENCHMARK_PLAYERS = 10

# A champion needs this many jungle games from the tracked player to be a target.
MIN_TARGET_CHAMPION_GAMES = 5
