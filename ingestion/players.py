"""Which synced player a request is about.

The server always picks the player: a request names one by PUUID, or gets the
owner. The model never sees or chooses a PUUID.
"""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

ROLE_NAMES = {
    "TOP": "top",
    "JUNGLE": "jungle",
    "MIDDLE": "mid",
    "BOTTOM": "bot",
    "UTILITY": "support",
}


@dataclass(frozen=True)
class SelectedPlayer:
    puuid: str
    game_name: str
    tag_line: str
    is_owner: bool
    # Current solo/duo tier, or None if unranked or never checked.
    rank_tier: str | None
    rank_checked: bool
    # The role in most of their ranked games, or None with no games.
    main_role: str | None
    # Ranked games per role.
    role_games: dict[str, int] = field(default_factory=dict)


PLAYERS = """
WITH roles AS (
    SELECT p.puuid, p.team_position,
           count(*) AS games,
           row_number() OVER (
               PARTITION BY p.puuid ORDER BY count(*) DESC, p.team_position
           ) AS place
    FROM match_participants p
    JOIN matches m ON m.match_id = p.match_id
    WHERE NOT m.is_remake AND p.team_position <> ''
      AND p.puuid IN (SELECT puuid FROM players)
    GROUP BY p.puuid, p.team_position
)
SELECT pl.puuid, pl.game_name, pl.tag_line, pl.is_owner, pl.rank_tier,
       pl.last_synced_at, pl.rank_checked_at,
       r.team_position AS main_role,
       coalesce((SELECT sum(games) FROM roles a WHERE a.puuid = pl.puuid), 0)::int AS games,
       coalesce(
           (SELECT games FROM roles a WHERE a.puuid = pl.puuid AND a.team_position = 'JUNGLE'),
           0
       )::int AS jungle_games,
       coalesce(
           (SELECT jsonb_object_agg(a.team_position, a.games) FROM roles a WHERE a.puuid = pl.puuid),
           '{}'
       ) AS role_games
FROM players pl
LEFT JOIN roles r ON r.puuid = pl.puuid AND r.place = 1
ORDER BY pl.is_owner DESC, lower(pl.game_name)
"""


async def list_players(session: AsyncSession) -> list[dict[str, Any]]:
    """Every synced player, the owner first, with games, main role and rank."""
    return [dict(row) for row in (await session.execute(text(PLAYERS))).mappings()]


async def load_player(session: AsyncSession, puuid: str | None = None) -> SelectedPlayer | None:
    """The player with this PUUID, or the owner when none is given. None if missing."""
    for row in await list_players(session):
        if (row["puuid"] == puuid) if puuid else row["is_owner"]:
            return SelectedPlayer(
                puuid=row["puuid"],
                game_name=row["game_name"],
                tag_line=row["tag_line"],
                is_owner=row["is_owner"],
                rank_tier=row["rank_tier"],
                rank_checked=row["rank_checked_at"] is not None,
                main_role=row["main_role"],
                role_games=row["role_games"],
            )
    return None
