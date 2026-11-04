"""The champion-select board: what the player's team lacks, and which of the
player's own jungle champions fill each gap.

It shows; it doesn't pick. Riot's League policy lists "Apps that dictate player
decisions" as unapproved, so nothing here ranks champions or names a best one.

It only takes what champion select shows on screen: the champions picked and
banned. No other player's identity, rank or history goes in.

The gaps are rules over Data Dragon's static data (tags and Riot's 0-10
ratings), not stats from games. The pool's games and win rates come from
champion_stats. Matchups are never estimated: see NO_MATCHUP_DATA.
"""

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from analytics.stats import Row, Scope, champion_stats
from ingestion.models import Champion

# A champion needs this many of the player's jungle games to be in the pool.
MIN_POOL_GAMES = 3

MAX_ALLIES = 4  # the player is the fifth
MAX_ENEMIES = 5
MAX_BANS = 10

NO_MATCHUP_DATA = (
    "No matchup data. A win rate for one champion against another needs many "
    "games of that exact pair, far more than the player's games or the benchmark "
    "sample have, so none is given or estimated."
)


def damage_type(champion: Champion) -> str:
    """physical, magic or mixed, from Riot's attack and magic ratings."""
    if champion.magic > champion.attack:
        return "magic"
    if champion.attack > champion.magic:
        return "physical"
    return "mixed"


@dataclass(frozen=True)
class Gap:
    id: str
    description: str

    def missing(self, team: list[Champion]) -> bool:
        return not RULES[self.id](team)

    def added_by(self, team: list[Champion], champion: Champion) -> bool:
        """The team lacks it, and has it with this champion: the rule decides, so a
        lone Fighter only adds a frontline to a team that already has a Fighter."""
        return self.missing(team) and not self.missing([*team, champion])


def _has_frontline(team: list[Champion]) -> bool:
    fighters = sum("Fighter" in c.tags for c in team)
    return any("Tank" in c.tags for c in team) or fighters >= 2


def _deals(kind: str):
    def check(team: list[Champion]) -> bool:
        return any(damage_type(c) in (kind, "mixed") for c in team)

    return check


# Each rule: does the team have it?
RULES = {
    "no_frontline": _has_frontline,
    "no_magic_damage": _deals("magic"),
    "no_physical_damage": _deals("physical"),
}
GAPS = (
    Gap("no_frontline", "No frontline: no Tank, and fewer than two Fighters."),
    Gap(
        "no_magic_damage",
        "No magic damage: no champion Riot rates higher for magic than attack, "
        "or equal for both.",
    ),
    Gap(
        "no_physical_damage",
        "No physical damage: no champion Riot rates higher for attack than magic, "
        "or equal for both.",
    ),
)


def _key(name: str) -> str:
    return re.sub(r"[^a-z]", "", name.lower())


def resolve(names: list[str], champions: dict[str, Champion]) -> list[Champion]:
    """Champions by Data Dragon id or display name, ignoring case and punctuation."""
    lookup = {}
    for champion in champions.values():
        lookup[_key(champion.champion)] = champion
        lookup[_key(champion.name)] = champion
    unknown = [name for name in names if _key(name) not in lookup]
    if unknown:
        raise ValueError(f"Unknown champions: {', '.join(unknown)}.")
    return [lookup[_key(name)] for name in names]


def _describe(champion: Champion) -> Row:
    return {
        "champion": champion.champion,
        "name": champion.name,
        "tags": list(champion.tags),
        "damage": damage_type(champion),
        "attack_rating": champion.attack,
        "magic_rating": champion.magic,
    }


def _check_board(allies: list[Champion], enemies: list[Champion], bans: list[Champion]) -> None:
    for label, given, most in (
        ("your team", allies, MAX_ALLIES),
        ("the enemy team", enemies, MAX_ENEMIES),
        ("bans", bans, MAX_BANS),
    ):
        if len(given) > most:
            raise ValueError(f"At most {most} champions for {label}.")
    picked = [c.champion for c in allies + enemies]
    twice = sorted({c for c in picked if picked.count(c) > 1})
    if twice:
        raise ValueError(f"A champion can only be picked once: {', '.join(twice)}.")
    banned_and_picked = sorted({c.champion for c in bans} & set(picked))
    if banned_and_picked:
        raise ValueError(f"Banned champions can't be picked: {', '.join(banned_and_picked)}.")


async def draft_board(
    session: AsyncSession,
    puuids: tuple[str, ...] | list[str],
    champions: dict[str, Champion],
    allies: list[str],
    enemies: list[str],
    bans: list[str],
) -> Row:
    """The board for one moment of champion select. Raises ValueError on bad input."""
    team = resolve(allies, champions)
    enemy = resolve(enemies, champions)
    banned = resolve(bans, champions)
    _check_board(team, enemy, banned)

    gaps = [gap for gap in GAPS if team and gap.missing(team)]
    taken = {c.champion: "picked" for c in team + enemy} | {
        c.champion: "banned" for c in banned
    }

    by_id = {key.lower(): champion for key, champion in champions.items()}
    rows = await champion_stats(session, Scope(puuids=tuple(puuids), role="JUNGLE"))
    pool = []
    for row in rows:
        if row["games"] < MIN_POOL_GAMES:
            continue
        # Match data and Data Dragon don't always agree on case (FiddleSticks).
        static = by_id.get(row["champion"].lower())
        entry = {
            "champion": row["champion"],
            "games": row["games"],
            "wins": row["wins"],
            "win_rate_pct": row["win_rate_pct"],
            "margin_win_rate_pct": row["margin_win_rate_pct"],
            "low_sample": row["low_sample"],
        }
        if static:
            # Data Dragon's id from here on: picks and bans use it, and so do icons.
            entry |= _describe(static)
        if entry["champion"] in taken:
            entry["unavailable"] = taken[entry["champion"]]
        elif static:
            entry["fills"] = [gap.id for gap in gaps if gap.added_by(team, static)]
        pool.append(entry)

    notes = [
        f"The pool is the player's jungle champions with {MIN_POOL_GAMES} or more "
        "games, most played first. It is not a ranking.",
    ]
    if not team:
        notes.append("Nothing is picked on the player's team yet, so no gaps are checked.")
    return {
        "your_team": [_describe(c) for c in team],
        "enemy_team": [_describe(c) | {"matchup": "no_matchup_data"} for c in enemy],
        "bans": [c.champion for c in banned],
        "rules_checked": [gap.description for gap in GAPS],
        "gaps": [
            {
                "gap": gap.id,
                "description": gap.description,
                "filled_by": [
                    p["champion"] for p in pool if gap.id in p.get("fills", [])
                ],
            }
            for gap in gaps
        ],
        "pool": pool,
        "matchups": NO_MATCHUP_DATA,
        "notes": notes,
    }


def draft_board_inputs(arguments: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    """The three champion lists from a request or tool call, missing ones empty."""
    return tuple(list(arguments.get(key) or []) for key in ("allies", "enemies", "bans"))
