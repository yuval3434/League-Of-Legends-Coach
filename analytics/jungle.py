"""Jungle stats. Each one covers only games the player spent in the jungle.

The rules in analytics/stats.py apply here too. DECISIONS.md explains why ward
events are filtered, why neutral objective kills are dropped, and why there's
no "first gank" stat.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from analytics.stats import Players, Row, fetch

# One row per player per game. No timeline means unknown events, not zero.
JUNGLE_GAMES = """
WITH jungle_games AS (
    SELECT p.match_id, p.participant_id, p.team_id, p.kills, p.assists, m.duration_s
    FROM match_participants p
    JOIN matches m ON m.match_id = p.match_id
    WHERE p.puuid = ANY(:puuids)
      AND NOT m.is_remake
      AND p.team_position = 'JUNGLE'
      AND EXISTS (SELECT 1 FROM timeline_frames f WHERE f.match_id = m.match_id)
)
"""

# Each objective kill, seen from one player's team. killerTeamId 300 means
# neither team took it. Elder gets its own name because it's worth far more
# than a regular dragon.
OBJECTIVE_KILLS = """
objective_kills AS (
    SELECT j.match_id, j.participant_id, j.team_id, e.timestamp_ms,
           CASE WHEN e.data->>'monsterSubType' = 'ELDER_DRAGON' THEN 'ELDER_DRAGON'
                ELSE e.data->>'monsterType'
           END AS objective,
           (e.data->>'killerTeamId')::int = j.team_id AS by_my_team,
           e.actor_id = j.participant_id AS my_last_hit
    FROM jungle_games j
    JOIN timeline_events e
      ON  e.match_id = j.match_id
      AND e.type = 'ELITE_MONSTER_KILL'
      AND e.data->>'killerTeamId' IN ('100', '200')
)
"""

OBJECTIVE_CONTROL = (
    JUNGLE_GAMES
    + ","
    + OBJECTIVE_KILLS
    + """,
per_game AS (
    -- Every game gets a row for every objective, so games with none count.
    SELECT j.match_id, j.participant_id, o.objective,
           count(k.match_id) FILTER (WHERE k.by_my_team) AS team_taken,
           count(k.match_id) FILTER (WHERE NOT k.by_my_team) AS enemy_taken,
           count(k.match_id) FILTER (WHERE k.my_last_hit) AS my_last_hits
    FROM jungle_games j
    CROSS JOIN (SELECT DISTINCT objective FROM objective_kills) o
    LEFT JOIN objective_kills k
      ON  k.match_id = j.match_id
      AND k.participant_id = j.participant_id
      AND k.objective = o.objective
    GROUP BY j.match_id, j.participant_id, o.objective
)
SELECT objective,
       count(*) AS games,
       sum(team_taken)::int AS team_taken,
       sum(enemy_taken)::int AS enemy_taken,
       sum(team_taken + enemy_taken)::int AS objectives,
       round(100.0 * sum(team_taken) / nullif(sum(team_taken + enemy_taken), 0), 1)
           AS team_share_pct,
       round(avg(team_taken), 2) AS avg_team_taken,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY team_taken)::numeric, 1)
           AS median_team_taken,
       round(avg(enemy_taken), 2) AS avg_enemy_taken,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY enemy_taken)::numeric, 1)
           AS median_enemy_taken,
       sum(my_last_hits)::int AS my_last_hits
FROM per_game
GROUP BY objective
ORDER BY objective
"""
)


async def objective_control(session: AsyncSession, puuids: Players) -> list[Row]:
    """Objectives taken by the player's team vs. the enemy's, per objective.

    `objective` is Riot's monsterType, or ELDER_DRAGON. A new monster type gets
    its own row. HORDE counts each void grub, not each group.
    """
    return await fetch(session, OBJECTIVE_CONTROL, puuids=puuids)


DEATHS_BEFORE_OBJECTIVE = (
    JUNGLE_GAMES
    + ","
    + OBJECTIVE_KILLS
    + """,
moments AS (
    SELECT match_id, participant_id, team_id, timestamp_ms, objective,
           CASE WHEN by_my_team THEN 'team' ELSE 'enemy' END AS taken_by
    FROM objective_kills
    UNION ALL
    -- The baseline: ordinary one-minute marks from minute 5, when objectives
    -- start to matter. It shows how often a death falls in any 60-second window.
    SELECT j.match_id, j.participant_id, j.team_id, f.timestamp_ms,
           'baseline', NULL
    FROM jungle_games j
    JOIN timeline_frames f
      ON  f.match_id = j.match_id
      AND f.participant_id = j.participant_id
      AND f.minute >= 5
),
counted AS (
    SELECT mo.match_id, mo.participant_id, mo.objective, mo.taken_by,
           count(d.match_id) FILTER (WHERE d.victim_id = mo.participant_id) AS my_deaths,
           count(d.match_id) AS team_deaths
    FROM moments mo
    LEFT JOIN (
        timeline_events d
        JOIN match_participants v
          ON v.match_id = d.match_id AND v.participant_id = d.victim_id
    )
      ON  d.match_id = mo.match_id
      AND d.type = 'CHAMPION_KILL'
      AND d.timestamp_ms BETWEEN mo.timestamp_ms - 60000 AND mo.timestamp_ms
      AND v.team_id = mo.team_id
    GROUP BY mo.match_id, mo.participant_id, mo.team_id, mo.timestamp_ms,
             mo.objective, mo.taken_by
),
baseline AS (
    SELECT count(*) AS windows,
           round(100.0 * count(*) FILTER (WHERE my_deaths > 0) / nullif(count(*), 0), 1)
               AS my_death_pct,
           round(100.0 * count(*) FILTER (WHERE team_deaths > 0) / nullif(count(*), 0), 1)
               AS team_death_pct
    FROM counted
    WHERE objective = 'baseline'
)
SELECT c.objective, c.taken_by,
       count(DISTINCT (c.match_id, c.participant_id)) AS games,
       count(*) AS objectives,
       round(100.0 * count(*) FILTER (WHERE c.my_deaths > 0) / count(*), 1)
           AS my_death_pct,
       round(100.0 * count(*) FILTER (WHERE c.team_deaths > 0) / count(*), 1)
           AS team_death_pct,
       round(avg(c.team_deaths), 2) AS avg_team_deaths,
       b.my_death_pct AS baseline_my_death_pct,
       b.team_death_pct AS baseline_team_death_pct,
       b.windows AS baseline_windows
FROM counted c
CROSS JOIN baseline b
WHERE c.objective <> 'baseline'
GROUP BY c.objective, c.taken_by, b.my_death_pct, b.team_death_pct, b.windows
ORDER BY c.objective, c.taken_by
"""
)


async def deaths_before_objective(
    session: AsyncSession, puuids: Players
) -> list[Row]:
    """How often deaths came in the 60 seconds before an objective was taken.

    `taken_by` is 'team' or 'enemy'. `my_death_pct` is the share of objectives
    with a death of the player's in that window, and `team_death_pct` the same
    for anyone on their team, including them. Compare both with the `baseline_`
    columns, the same measure over ordinary 60-second windows from minute 5.

    `objectives` is the sample behind the percentages, and `games` drives
    `low_sample`. Void grubs die together, so one death can count for several
    HORDE rows. This shows the two happen together, not that one caused the other.
    """
    return await fetch(session, DEATHS_BEFORE_OBJECTIVE, puuids=puuids)


KILL_PARTICIPATION = (
    JUNGLE_GAMES
    + """,
team_kills AS (
    SELECT match_id, team_id, sum(kills) AS kills
    FROM match_participants
    GROUP BY match_id, team_id
),
per_game AS (
    SELECT 100.0 * (j.kills + j.assists) / t.kills AS kill_participation
    FROM jungle_games j
    JOIN team_kills t ON t.match_id = j.match_id AND t.team_id = j.team_id
    WHERE t.kills > 0
)
SELECT count(*) AS games,
       round(avg(kill_participation), 1) AS avg_kill_participation_pct,
       round(
           percentile_cont(0.5) WITHIN GROUP (ORDER BY kill_participation)::numeric, 1
       ) AS median_kill_participation_pct
FROM per_game
HAVING count(*) > 0
"""
)


async def kill_participation(session: AsyncSession, puuids: Players) -> list[Row]:
    """Share of the team's kills the player took part in, per game.

    Games where the team got no kills are left out, because the share is undefined.
    """
    return await fetch(session, KILL_PARTICIPATION, puuids=puuids)


WARDS_PER_MINUTE = (
    JUNGLE_GAMES
    + """,
per_game AS (
    SELECT j.match_id,
           count(e.match_id) FILTER (WHERE e.type = 'WARD_PLACED') AS placed,
           count(e.match_id) FILTER (WHERE e.type = 'WARD_KILL') AS destroyed,
           j.duration_s / 60.0 AS minutes
    FROM jungle_games j
    LEFT JOIN timeline_events e
      ON  e.match_id = j.match_id
      AND e.actor_id = j.participant_id
      AND e.type IN ('WARD_PLACED', 'WARD_KILL')
      AND e.data->>'wardType' NOT IN ('UNDEFINED', 'TEEMO_MUSHROOM')
    GROUP BY j.match_id, j.participant_id, j.duration_s
)
SELECT count(*) AS games,
       sum(placed)::int AS placed,
       sum(destroyed)::int AS destroyed,
       round(avg(placed / minutes), 3) AS avg_placed_per_min,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY placed / minutes)::numeric, 3)
           AS median_placed_per_min,
       round(avg(destroyed / minutes), 3) AS avg_destroyed_per_min,
       round(
           percentile_cont(0.5) WITHIN GROUP (ORDER BY destroyed / minutes)::numeric, 3
       ) AS median_destroyed_per_min
FROM per_game
HAVING count(*) > 0
"""
)


async def wards_per_minute(session: AsyncSession, puuids: Players) -> list[Row]:
    """Wards placed and destroyed per minute by the player.

    Leaves out Riot's UNDEFINED events and Teemo mushrooms, which don't count
    as wards in Riot's own end-of-game totals.
    """
    return await fetch(session, WARDS_PER_MINUTE, puuids=puuids)


FIRST_LANE_KILL = (
    JUNGLE_GAMES
    + """,
kills AS (
    SELECT j.match_id, j.participant_id, e.timestamp_ms, v.team_position AS victim_role,
           -- Zones are checked against Riot's turret positions; see DECISIONS.md.
           CASE
               WHEN (e.position_x < 4700 AND e.position_y < 4700)
                 OR (e.position_x > 10200 AND e.position_y > 10200) THEN 'base'
               WHEN e.position_x < 2000 OR e.position_y > 13000
                 OR (e.position_x < 5500 AND e.position_y > 9500) THEN 'top'
               WHEN e.position_y < 2000 OR e.position_x > 13000
                 OR (e.position_y < 5500 AND e.position_x > 9500) THEN 'bot'
               WHEN abs(e.position_x - e.position_y) < 2000 THEN 'mid'
               ELSE 'jungle'
           END AS zone
    FROM jungle_games j
    JOIN timeline_events e
      ON  e.match_id = j.match_id
      AND e.type = 'CHAMPION_KILL'
      AND e.timestamp_ms < 900000
      AND (e.actor_id = j.participant_id
           OR e.data->'assistingParticipantIds' @> to_jsonb(j.participant_id))
    JOIN match_participants v
      ON  v.match_id = e.match_id
      AND v.participant_id = e.victim_id
      AND v.team_id <> j.team_id
),
first_kills AS (
    -- A kill counts only if the victim was in their own lane.
    SELECT DISTINCT ON (match_id, participant_id)
           match_id, participant_id, timestamp_ms, victim_role, zone
    FROM kills
    WHERE (victim_role = 'TOP' AND zone = 'top')
       OR (victim_role = 'MIDDLE' AND zone = 'mid')
       OR (victim_role IN ('BOTTOM', 'UTILITY') AND zone = 'bot')
    ORDER BY match_id, participant_id, timestamp_ms
)
SELECT coalesce(f.zone, 'none') AS lane,
       f.victim_role,
       count(*) AS games,
       (sum(count(*)) OVER ())::int AS total_games,
       round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS share_pct,
       count(*) FILTER (WHERE f.timestamp_ms < 600000) AS games_before_10,
       round(avg(f.timestamp_ms) / 60000, 1) AS avg_minute,
       round(
           (percentile_cont(0.5) WITHIN GROUP (ORDER BY f.timestamp_ms) / 60000)::numeric,
           1
       ) AS median_minute
FROM jungle_games j
LEFT JOIN first_kills f
  ON f.match_id = j.match_id AND f.participant_id = j.participant_id
GROUP BY f.zone, f.victim_role
ORDER BY f.zone IS NULL, games DESC
"""
)


async def first_lane_kill(session: AsyncSession, puuids: Players) -> list[Row]:
    """The player's first kill or assist on a laner in their lane, before 15:00.

    One row per lane and victim role, plus lane 'none' for games with no such
    kill. Failed ganks don't appear, because the timeline records only kills, so
    'none' doesn't mean the player never ganked. `total_games` is every jungle
    game with a timeline.
    """
    return await fetch(session, FIRST_LANE_KILL, puuids=puuids)
