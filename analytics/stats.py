"""Stat functions. All the maths is SQL; each function becomes an agent tool.

Rules every stat follows:
- It takes a list of PUUIDs and pools their games, so with several players
  `games` counts player-games: two listed players in one match count twice.
  It can take a Scope instead, to narrow the games or use a benchmark sample.
- Every row has `games`, and `low_sample` is true below MIN_GAMES.
- A `margin_x` column is the 95% margin of error on `avg_x`. It's empty for
  a single game.
- Remakes are excluded.
"""

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

Row = dict[str, Any]

MIN_GAMES = 10

# A loss this long before the next game doesn't count towards a streak.
SESSION_BREAK_HOURS = 6

# Every stat picks its player's rows with this line of SQL.
PLAYER_FILTER = re.compile(r"(\w+)\.puuid = ANY\(:puuids\)")


@dataclass(frozen=True)
class Scope:
    """Which games a stat covers: `puuids`, or a benchmark `cohort`'s sample.

    A cohort needs a session on the benchmark schema, whose `sample` table lists
    the one player used from each match. With no `champion`, it uses the rows
    counted towards the all-champion benchmark.
    """

    puuids: tuple[str, ...] = ()
    cohort: str | None = None
    role: str | None = None
    champion: str | None = None
    patches: tuple[str, ...] | None = None

    def apply(self, query: str) -> tuple[str, dict[str, Any]]:
        """Swap the query's player filter for this scope's conditions."""
        params: dict[str, Any] = {}

        def conditions(match: re.Match[str]) -> str:
            alias = match[1]
            if self.cohort:
                rows = "cohort = :scope_cohort"
                params["scope_cohort"] = self.cohort
                rows += " AND champion_name = :scope_champion" if self.champion else (
                    " AND in_overall"
                )
                parts = [
                    f"({alias}.match_id, {alias}.participant_id) IN "
                    f"(SELECT match_id, participant_id FROM sample WHERE {rows})"
                ]
            else:
                parts = [f"{alias}.puuid = ANY(:scope_puuids)"]
                params["scope_puuids"] = list(self.puuids)
            if self.champion:
                parts.append(f"{alias}.champion_name = :scope_champion")
                params["scope_champion"] = self.champion
            if self.role:
                parts.append(f"{alias}.team_position = :scope_role")
                params["scope_role"] = self.role
            if self.patches is not None:
                parts.append("m.patch = ANY(:scope_patches)")
                params["scope_patches"] = list(self.patches)
            return " AND ".join(parts)

        return PLAYER_FILTER.sub(conditions, query), params


Players = list[str] | Scope


async def fetch(session: AsyncSession, query: str, **params: Any) -> list[Row]:
    """Run a query and return JSON-friendly rows with the sample size flagged."""
    scope = params.get("puuids")
    if isinstance(scope, Scope):
        del params["puuids"]
        query, scope_params = scope.apply(query)
        params.update(scope_params)
    result = await session.execute(text(query), params)
    rows = [
        {k: float(v) if isinstance(v, Decimal) else v for k, v in row.items()}
        for row in result.mappings()
    ]
    for row in rows:
        row["low_sample"] = row["games"] < MIN_GAMES
    return rows


WIN_RATES = """
WITH games AS (
    SELECT p.champion_name, p.team_position, p.win
    FROM match_participants p
    JOIN matches m ON m.match_id = p.match_id
    WHERE p.puuid = ANY(:puuids) AND NOT m.is_remake
)
SELECT 'champion' AS dimension, champion_name AS value,
       count(*) AS games,
       count(*) FILTER (WHERE win) AS wins,
       round(100.0 * count(*) FILTER (WHERE win) / count(*), 1) AS win_rate_pct
FROM games
GROUP BY champion_name
UNION ALL
SELECT 'role', team_position,
       count(*),
       count(*) FILTER (WHERE win),
       round(100.0 * count(*) FILTER (WHERE win) / count(*), 1)
FROM games
WHERE team_position <> ''
GROUP BY team_position
ORDER BY dimension, games DESC, value
"""


async def win_rates(session: AsyncSession, puuids: Players) -> list[Row]:
    """Win rate per champion and per role, told apart by `dimension`."""
    return await fetch(session, WIN_RATES, puuids=puuids)


DEATHS_BY_PHASE = """
WITH phases(phase, start_s, end_s) AS (
    VALUES ('early', 0, 900), ('mid', 900, 1500), ('late', 1500, NULL)
),
player_phases AS (
    -- One row per game per phase the game reached, so a phase with no deaths
    -- still counts as a game. No timeline means unknown deaths, not zero.
    SELECT p.match_id, p.participant_id, ph.phase, ph.start_s, ph.end_s,
           (least(m.duration_s, coalesce(ph.end_s, m.duration_s)) - ph.start_s)
               / 60.0 AS minutes
    FROM match_participants p
    JOIN matches m ON m.match_id = p.match_id
    JOIN phases ph ON m.duration_s >= ph.start_s
    WHERE p.puuid = ANY(:puuids)
      AND NOT m.is_remake
      AND EXISTS (SELECT 1 FROM timeline_frames f WHERE f.match_id = m.match_id)
),
phase_deaths AS (
    SELECT pp.phase, pp.start_s, pp.minutes, count(e.match_id) AS deaths
    FROM player_phases pp
    LEFT JOIN timeline_events e
      ON  e.match_id = pp.match_id
      AND e.type = 'CHAMPION_KILL'
      AND e.victim_id = pp.participant_id
      AND e.timestamp_ms >= pp.start_s * 1000
      AND (pp.end_s IS NULL OR e.timestamp_ms < pp.end_s * 1000)
    GROUP BY pp.match_id, pp.participant_id, pp.phase, pp.start_s, pp.end_s,
             pp.minutes
)
SELECT phase,
       count(*) AS games,
       sum(deaths)::int AS deaths,
       round(avg(deaths), 2) AS avg_deaths,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY deaths)::numeric, 2)
           AS median_deaths,
       round(10 * sum(deaths) / nullif(sum(minutes), 0), 2) AS deaths_per_10_min
FROM phase_deaths
GROUP BY phase, start_s
ORDER BY start_s
"""


async def deaths_by_phase(session: AsyncSession, puuids: Players) -> list[Row]:
    """Deaths in the early (<15:00), mid (15:00-25:00) and late (25:00+) game.

    `games` counts only games that reached the phase. Use `deaths_per_10_min`
    to compare phases, because they last different lengths.
    """
    return await fetch(session, DEATHS_BY_PHASE, puuids=puuids)


LANE_DIFF = """
WITH checkpoints(minute) AS (VALUES (10), (15), (20)),
lane_matchups AS (
    -- The opponent is the player in the same role on the other team.
    SELECT me.match_id, me.team_position, me.win, m.duration_s,
           me.participant_id AS my_id, opp.participant_id AS opp_id
    FROM match_participants me
    JOIN matches m ON m.match_id = me.match_id
    JOIN match_participants opp
      ON  opp.match_id = me.match_id
      AND opp.team_position = me.team_position
      AND opp.team_id <> me.team_id
    WHERE me.puuid = ANY(:puuids)
      AND NOT m.is_remake
      AND me.team_position <> ''
),
diffs AS (
    SELECT l.team_position, l.win, c.minute,
           mine.total_gold - theirs.total_gold AS gold_diff,
           (mine.lane_cs + mine.jungle_cs)
               - (theirs.lane_cs + theirs.jungle_cs) AS cs_diff
    FROM lane_matchups l
    CROSS JOIN checkpoints c
    JOIN timeline_frames mine
      ON  mine.match_id = l.match_id
      AND mine.participant_id = l.my_id
      AND mine.minute = c.minute
    JOIN timeline_frames theirs
      ON  theirs.match_id = l.match_id
      AND theirs.participant_id = l.opp_id
      AND theirs.minute = c.minute
    -- `minute` is a frame's position, and the last frame lands on the game's
    -- end, so a game ending at 14:50 has a frame numbered 15.
    WHERE l.duration_s >= c.minute * 60
)
SELECT team_position AS role, minute,
       CASE WHEN GROUPING(win) = 1 THEN 'all' WHEN win THEN 'win' ELSE 'loss' END
           AS result,
       count(*) AS games,
       round(avg(gold_diff)) AS avg_gold_diff,
       round((1.96 * stddev(gold_diff) / sqrt(count(*)))::numeric, 0) AS margin_gold_diff,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY gold_diff)::numeric)
           AS median_gold_diff,
       round(avg(cs_diff), 1) AS avg_cs_diff,
       round((1.96 * stddev(cs_diff) / sqrt(count(*)))::numeric, 1) AS margin_cs_diff,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY cs_diff)::numeric, 1)
           AS median_cs_diff
FROM diffs
GROUP BY team_position, minute, GROUPING SETS ((), (win))
HAVING GROUPING(win) = 1 OR team_position = 'JUNGLE'
ORDER BY role, minute, result
"""


async def lane_diff(session: AsyncSession, puuids: Players) -> list[Row]:
    """Gold and CS difference vs. the lane opponent at minutes 10, 15 and 20.

    One row per role and minute with `result` 'all'; jungle also gets 'win' and
    'loss' rows. Those show how gaps relate to outcomes, not what caused them.
    Games that ended before a minute drop out of its rows, so `games` can fall
    as the minute rises.
    """
    return await fetch(session, LANE_DIFF, puuids=puuids)


WIN_RATE_BY_GOLD_DIFF = """
WITH buckets(bucket, position, low, high) AS (
    VALUES ('behind 500+', 1, NULL, -500),
           ('behind 0-500', 2, -500, 0),
           ('ahead 0-500', 3, 0, 500),
           ('ahead 500+', 4, 500, NULL)
),
gold_at_10 AS (
    SELECT me.win, mine.total_gold - theirs.total_gold AS gold_diff
    FROM match_participants me
    JOIN matches m ON m.match_id = me.match_id
    JOIN match_participants opp
      ON  opp.match_id = me.match_id
      AND opp.team_position = me.team_position
      AND opp.team_id <> me.team_id
    JOIN timeline_frames mine
      ON  mine.match_id = me.match_id
      AND mine.participant_id = me.participant_id
      AND mine.minute = 10
    JOIN timeline_frames theirs
      ON  theirs.match_id = me.match_id
      AND theirs.participant_id = opp.participant_id
      AND theirs.minute = 10
    WHERE me.puuid = ANY(:puuids)
      AND NOT m.is_remake
      AND me.team_position = 'JUNGLE'
      AND m.duration_s >= 600
)
SELECT b.bucket,
       count(g.gold_diff) AS games,
       count(*) FILTER (WHERE g.win) AS wins,
       round(100.0 * count(*) FILTER (WHERE g.win) / nullif(count(g.gold_diff), 0), 1)
           AS win_rate_pct
FROM buckets b
LEFT JOIN gold_at_10 g
  ON  (b.low IS NULL OR g.gold_diff >= b.low)
  AND (b.high IS NULL OR g.gold_diff < b.high)
GROUP BY b.bucket, b.position
ORDER BY b.position
"""


async def win_rate_by_gold_diff(session: AsyncSession, puuids: Players) -> list[Row]:
    """Jungle win rate by gold difference vs. the enemy jungler at minute 10.

    Every bucket is returned, with `win_rate_pct` null if it has no games.
    Exactly -500 is 'behind 0-500', 0 is 'ahead 0-500' and 500 is 'ahead 500+'.
    """
    return await fetch(session, WIN_RATE_BY_GOLD_DIFF, puuids=puuids)


AFTER_LOSS_STREAK = """
WITH games AS (
    SELECT p.puuid, m.game_start_at, p.win, p.deaths,
           (p.kills + p.assists)::numeric / greatest(p.deaths, 1) AS kda,
           m.game_start_at + make_interval(secs => m.duration_s) AS ended_at
    FROM match_participants p
    JOIN matches m ON m.match_id = p.match_id
    WHERE p.puuid = ANY(:puuids) AND NOT m.is_remake
),
with_previous AS (
    SELECT *, lag(win) OVER w AS previous_win, lag(ended_at) OVER w AS previous_end
    FROM games
    WINDOW w AS (PARTITION BY puuid ORDER BY game_start_at)
),
streaks AS (
    -- A new streak starts after a win, after a long break, or at the first game.
    SELECT *,
           count(*) FILTER (
               WHERE previous_win IS NOT FALSE
                  OR game_start_at - previous_end
                     >= make_interval(hours => :break_hours)
           ) OVER (PARTITION BY puuid ORDER BY game_start_at) AS streak_id
    FROM with_previous
),
counted AS (
    SELECT *,
           row_number() OVER (PARTITION BY puuid, streak_id ORDER BY game_start_at) - 1
               AS previous_losses
    FROM streaks
)
SELECT CASE WHEN previous_losses >= 3 THEN '3+' ELSE previous_losses::text END
           AS losses_before,
       count(*) AS games,
       count(*) FILTER (WHERE win) AS wins,
       round(100.0 * count(*) FILTER (WHERE win) / count(*), 1) AS win_rate_pct,
       round(avg(deaths), 2) AS avg_deaths,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY deaths)::numeric, 1)
           AS median_deaths,
       round(avg(kda), 2) AS avg_kda,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY kda)::numeric, 2)
           AS median_kda
FROM counted
GROUP BY 1
ORDER BY 1
"""


async def after_loss_streak(session: AsyncSession, puuids: Players) -> list[Row]:
    """Performance by how many losses came straight before the game.

    `losses_before` is '0', '1', '2' or '3+'; '0' is the baseline to compare
    with. A win or a break of SESSION_BREAK_HOURS resets the streak.
    """
    return await fetch(
        session, AFTER_LOSS_STREAK, puuids=puuids, break_hours=SESSION_BREAK_HOURS
    )


CS_PER_MINUTE = """
WITH games AS (
    SELECT p.team_position, m.patch,
           (p.lane_cs + p.jungle_cs) / (m.duration_s / 60.0) AS cs_per_min
    FROM match_participants p
    JOIN matches m ON m.match_id = p.match_id
    WHERE p.puuid = ANY(:puuids)
      AND NOT m.is_remake
      AND p.team_position <> ''
)
SELECT team_position AS role, patch,
       count(*) AS games,
       round(avg(cs_per_min), 2) AS avg_cs_per_min,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY cs_per_min)::numeric, 2)
           AS median_cs_per_min
FROM games
GROUP BY team_position, patch
ORDER BY role, string_to_array(patch, '.')::int[]
"""


async def cs_per_minute(session: AsyncSession, puuids: Players) -> list[Row]:
    """CS per minute per role and patch, oldest patch first.

    CS includes jungle camps. Roles are kept apart because their CS isn't
    comparable.
    """
    return await fetch(session, CS_PER_MINUTE, puuids=puuids)


OVERALL_CS_PER_MINUTE = """
WITH games AS (
    SELECT p.team_position,
           (p.lane_cs + p.jungle_cs) / (m.duration_s / 60.0) AS cs_per_min
    FROM match_participants p
    JOIN matches m ON m.match_id = p.match_id
    WHERE p.puuid = ANY(:puuids)
      AND NOT m.is_remake
      AND p.team_position <> ''
)
SELECT team_position AS role,
       count(*) AS games,
       round(avg(cs_per_min), 2) AS avg_cs_per_min,
       round((1.96 * stddev(cs_per_min) / sqrt(count(*)))::numeric, 2) AS margin_cs_per_min,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY cs_per_min)::numeric, 2)
           AS median_cs_per_min
FROM games
GROUP BY team_position
ORDER BY role
"""


async def overall_cs_per_minute(session: AsyncSession, puuids: Players) -> list[Row]:
    """CS per minute per role across all the games, for comparing with a benchmark."""
    return await fetch(session, OVERALL_CS_PER_MINUTE, puuids=puuids)


GOLD_CS_AT_MINUTE = """
WITH checkpoints(minute) AS (VALUES (10), (15), (20)),
values_at AS (
    SELECT p.team_position, c.minute, f.total_gold AS gold,
           f.lane_cs + f.jungle_cs AS cs
    FROM match_participants p
    JOIN matches m ON m.match_id = p.match_id
    CROSS JOIN checkpoints c
    JOIN timeline_frames f
      ON  f.match_id = p.match_id
      AND f.participant_id = p.participant_id
      AND f.minute = c.minute
    WHERE p.puuid = ANY(:puuids)
      AND NOT m.is_remake
      AND p.team_position <> ''
      -- `minute` is a frame's position; see lane_diff.
      AND m.duration_s >= c.minute * 60
)
SELECT team_position AS role, minute,
       count(*) AS games,
       round(avg(gold)) AS avg_gold,
       round((1.96 * stddev(gold) / sqrt(count(*)))::numeric, 0) AS margin_gold,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY gold)::numeric) AS median_gold,
       round(avg(cs), 1) AS avg_cs,
       round((1.96 * stddev(cs) / sqrt(count(*)))::numeric, 1) AS margin_cs,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY cs)::numeric, 1) AS median_cs
FROM values_at
GROUP BY team_position, minute
ORDER BY role, minute
"""


async def gold_cs_at_minute(session: AsyncSession, puuids: Players) -> list[Row]:
    """Total gold and CS at minutes 10, 15 and 20, per role.

    Unlike lane_diff, these don't depend on the opponent, so they can be compared
    with players of other ranks. CS includes jungle camps.
    """
    return await fetch(session, GOLD_CS_AT_MINUTE, puuids=puuids)
