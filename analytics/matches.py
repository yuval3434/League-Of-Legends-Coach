"""A player's recent games, and one game's two teams, for the Matches page.

These list games rather than summarise them, so they carry no margins. One game
shows what happened in it, nothing more: every per-game number is from SQL.

Only champions, roles and stats leave here: never another player's name or
PUUID, and only games the player was in.
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

Row = dict[str, Any]

MAX_LIMIT = 100

RECENT = """
SELECT m.match_id, m.game_start_at, m.duration_s, m.patch, m.queue_id, m.is_remake,
       p.champion_name AS champion, p.team_position AS role, p.win,
       p.kills, p.deaths, p.assists, p.lane_cs + p.jungle_cs AS cs
FROM match_participants p
JOIN matches m ON m.match_id = p.match_id
WHERE p.puuid = :puuid
ORDER BY m.game_start_at DESC, m.match_id
LIMIT :limit OFFSET :offset
"""

COUNT = "SELECT count(*) FROM match_participants WHERE puuid = :puuid"


async def recent_matches(
    session: AsyncSession, puuid: str, limit: int = 20, offset: int = 0
) -> Row:
    """The player's games, newest first, with the total so a page can go on."""
    limit = max(1, min(limit, MAX_LIMIT))
    params = {"puuid": puuid, "limit": limit, "offset": max(0, offset)}
    rows = (await session.execute(text(RECENT), params)).mappings().all()
    total = await session.scalar(text(COUNT), {"puuid": puuid})
    return {"matches": [dict(row) for row in rows], "total": total}


DETAIL = """
WITH me AS (
    SELECT match_id, team_id, participant_id
    FROM match_participants
    WHERE match_id = :match_id AND puuid = :puuid
)
SELECT CASE WHEN p.team_id = me.team_id THEN 'ally' ELSE 'enemy' END AS side,
       p.participant_id = me.participant_id AS is_me,
       p.team_position AS role, p.champion_name AS champion, p.win,
       p.kills, p.deaths, p.assists,
       p.lane_cs + p.jungle_cs AS cs,
       round((p.lane_cs + p.jungle_cs) / (m.duration_s / 60.0), 1) AS cs_per_min,
       p.gold_earned, p.damage_to_champions, p.vision_score
FROM me
JOIN match_participants p ON p.match_id = me.match_id
JOIN matches m ON m.match_id = me.match_id
ORDER BY p.team_id <> me.team_id,
         array_position(ARRAY['TOP', 'JUNGLE', 'MIDDLE', 'BOTTOM', 'UTILITY'], p.team_position),
         p.participant_id
"""

HEADER = """
SELECT match_id, game_start_at, duration_s, patch, queue_id, is_remake
FROM matches WHERE match_id = :match_id
"""


async def match_detail(session: AsyncSession, puuid: str, match_id: str) -> Row | None:
    """One game the player was in: its header and both teams. None if they weren't."""
    params = {"puuid": puuid, "match_id": match_id}
    players = (await session.execute(text(DETAIL), params)).mappings().all()
    if not players:
        return None
    header = (await session.execute(text(HEADER), params)).mappings().one()
    rows = [
        {k: float(v) if k == "cs_per_min" and v is not None else v for k, v in row.items()}
        for row in players
    ]
    return dict(header) | {"players": rows}
