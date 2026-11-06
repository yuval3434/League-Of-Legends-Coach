"""The benchmark cohorts and the sample sizes they must reach.

A cohort is one rank and one role, and its name says which: "gold_middle" is
Gold mid laners. Silver and Emerald junglers came first and keep their short
names. Any other cohort is peers: players of the same rank as the one it's
compared with. A cohort exists once its sample has rows; nothing else records it.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from analytics.stats import MIN_GAMES


@dataclass(frozen=True)
class Cohort:
    tier: str
    role: str
    # Peers share the player's opponent level, so stats measured against the
    # opponent mean the same on both sides. Higher tiers get absolute stats only.
    relative_stats: bool
    # "peers" is for players of this tier; "target" is for players below it.
    audience: str


ROLES = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")
ROLE_NAMES = {"TOP": "top", "JUNGLE": "jungle", "MIDDLE": "mid", "BOTTOM": "bot", "UTILITY": "support"}
# How a group of players in each role is called in a sentence.
ROLE_GROUPS = {
    "TOP": "top laners",
    "JUNGLE": "junglers",
    "MIDDLE": "mid laners",
    "BOTTOM": "bot laners",
    "UTILITY": "supports",
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
# The pull finds players on Riot's divided ladder, which stops at Diamond.
# Master and above are one league each, behind a different endpoint.
PULLABLE_TIERS = TIERS[: TIERS.index("DIAMOND") + 1]

# The first two cohorts, with their original names.
COHORTS = {
    "silver": Cohort(tier="SILVER", role="JUNGLE", relative_stats=True, audience="peers"),
    "emerald": Cohort(tier="EMERALD", role="JUNGLE", relative_stats=False, audience="target"),
}
# Emerald is a target for junglers only; outside the jungle, peers only.
TARGET_COHORTS = {"JUNGLE": "emerald"}


def peer_cohort(tier: str, role: str) -> str:
    """The name of the cohort of `tier` players in `role`."""
    for name, cohort in COHORTS.items():
        if (cohort.tier, cohort.role, cohort.audience) == (tier, role, "peers"):
            return name
    return f"{tier}_{role}".lower()


def get_cohort(name: str) -> Cohort | None:
    """The cohort a name stands for, or None if it names none."""
    if name in COHORTS:
        return COHORTS[name]
    tier, _, role = name.upper().partition("_")
    if tier not in TIERS or role not in ROLES or peer_cohort(tier, role) != name:
        return None
    return Cohort(tier=tier, role=role, relative_stats=True, audience="peers")


def cohorts_for(rank_tier: str | None, role: str) -> list[str]:
    """The cohorts that could fit a player of this rank in this role: peers, then a target."""
    names = []
    if rank_tier is not None:
        names.append(peer_cohort(rank_tier, role))
    target = TARGET_COHORTS.get(role)
    if target and target not in names:
        names.append(target)
    return names


def offered_roles(role_games: dict[str, int], main_role: str | None) -> list[str]:
    """The roles a player gets benchmarks in: their main role, and any with MIN_GAMES+ games."""
    roles = [main_role] if main_role else []
    for role, games in sorted(role_games.items(), key=lambda item: -item[1]):
        if games >= MIN_GAMES and role not in roles:
            roles.append(role)
    return roles


def why_no_benchmark(
    cohort: str, rank_tier: str | None, roles: Sequence[str], rank_checked: bool = True
) -> str | None:
    """Why a player can't be compared with `cohort`, or None if they can.

    `roles` are the roles the player gets benchmarks in (see offered_roles).
    A cohort is never swapped for another one: a player it doesn't fit gets no
    benchmark at all.
    """
    group = get_cohort(cohort)
    if group is None:
        return f"There's no cohort called {cohort}."
    name = group.tier.capitalize()
    if not roles:
        return "This player has no ranked games, so there's nothing to compare."
    if group.role not in roles:
        return (
            f"This benchmark is {ROLE_GROUPS[group.role]}, and this player has fewer than "
            f"{MIN_GAMES} {ROLE_NAMES[group.role]} games."
        )
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

# A champion needs this many games in the role from the player to be a target.
MIN_TARGET_CHAMPION_GAMES = 5
