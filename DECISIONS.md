# Decisions

Choices that change what a stat means. Numbers come from the first real sync:
100 ranked games, 96 after removing remakes (2026-03-22 to 2026-10-30).

## Loss streaks reset after a 6-hour break

**Decision:** `after_loss_streak` counts consecutive losses, and a win or a gap
of 6+ hours resets the count. The gap runs from the end of one game to the start
of the next. The value is `SESSION_BREAK_HOURS` in `analytics/stats.py`.

**Why:** the stat is meant to show how a player performs right after losing, and
a loss from last week can't affect that. Of the 54 games that followed a loss,
22 started 6+ hours later, and the longest gap between any two games is 74 days.
Without a reset, those games would count as continuing a streak.

**Why 6 hours:** gaps fall into two groups. 54 of the 95 gaps are under 1 hour,
9 are 1 to 6 hours, and 32 are 6+ hours. Six hours is long enough to cover a
short break in one session and short enough to split sessions on different
parts of a day. It's a judgement call, not a measured boundary.

**Cost:** fewer games land in the long-streak buckets: currently 6 games after
two losses and 1 after three or more.

## Game phases: early before 15:00, mid to 25:00, late after

**Decision:** `deaths_by_phase` uses early (under 15:00), mid (15:00 to 25:00)
and late (25:00 on). The boundaries are written in its SQL.

**Why 15:00:** it matches when these games start to end. Only 1 of the 96 games
finished before 15:00, while 7 surrendered between 15:13 and 16:16.

**Why 25:00:** the median game lasts 31 minutes and 75 of the 96 games reach
25:00, so the late phase has enough games to read.

**Limits:** these are conventional round numbers checked against the data, not
boundaries found in it. Phases last different lengths and not every game reaches
every phase, so compare them with `deaths_per_10_min`, not raw death counts.

## Phase 2.5: benchmark players must not be lane opponents in the same match

**Decision:** a benchmark uses one jungler per match per cohort. The primary key
of `benchmark.sample` is (cohort, match_id), so the database enforces this.

**Why:** stats pool the benchmark's games. If two benchmark players face each
other, one's +500 and the other's -500 cancel to 0, which pulls the benchmark
towards zero and hides the gap it's meant to measure. They would also count as
2 games, overstating the sample size.

**How the one jungler is chosen:** a target champion goes first, and otherwise a
hash of the match decides. The result is never looked at, because choosing by
who won would bias the win rate.

**Cost:** preferring target champions slightly over-represents them in the
all-champion benchmark.

## Benchmark cohorts: Silver as peers, Emerald as a target

**Decision:** two cohorts, stored separately and never pooled. Silver gets every
comparison. Emerald gets absolute stats only: gold and CS at 10, 15 and 20
minutes, CS per minute, deaths by phase, kill participation and wards per minute.
Master+ can be added later as a ceiling.

**Why these tiers:** the player is Silver IV. Master+ is too far away to act on,
and their main champions barely appear there: in 220 Master+ matches, Dr. Mundo
was in the jungle twice, Zaahen once and Shen never.

**Why Emerald gets no relative stats:** gold difference, win rate and objective
share are measured against the opponent. An Emerald jungler's +200 is against
Emerald opponents, so it can't be set beside a Silver player's number.

**Limit on Silver:** these stats are comparable, but across all champions the
average is fixed by the game itself: the two junglers' differences mirror each
other and every game has one winner, so it sits near 0 and 50%. The player's own
number, read against 0 and 50%, says the same thing. Silver's real value here is
per champion, where a champion's typical result can differ from 0 and 50%.
`compare` adds a note saying so.

## A benchmark needs 100 games to be a target, and 30 games and 10 players to exist

**Decision:** the pull aims for 500 games across all champions and 100 per target
champion (5+ jungle games from the player). Below 30 games or 10 distinct
players there is no benchmark, and the coach says so. Nothing is substituted. A
single row below 30 games, such as `loss` at minute 20, is also reported as no
benchmark. Each player counts for at most 10 games per champion.

**Why:** benchmark gold at minute 10 varies by about 530 from game to game, so
the 95% margin is about ±188 at 30 games, ±103 at 100 and ±46 at 500. Past 100
per champion, the player's own small sample is the limit: with 17 Dr. Mundo
games, going from 100 to 400 benchmark games only tightens a gold difference
comparison from about ±290 to ±260. The per-player cap stops one specialist from
becoming the benchmark.

**Reading a gap:** `compare` reports each average's margin, the gap, and
`clear_gap`, which is true when the gap is bigger than both margins combined.
Medians, deaths, win rate and objective share have no margin, so `clear_gap` is
empty for them. There are dozens of rows, so about 1 in 20 can show a clear gap
by chance. Rows split by win or loss rest on 11 to 16 of the player's games.

## No mastery top-up for rare champions

**Decision:** the pull finds players at random from the ladder only. It doesn't
use champion mastery to seek out players of rare champions, so Dr. Mundo, Zaahen
and Shen are likely to stay at "no benchmark".

**Why:** after 3,000 checked matches per cohort, Silver has 19 Dr. Mundo games,
8 Zaahen and 5 Shen, and Emerald has 10, 7 and 4. All are below the 30-game
floor. Mastery could fill that gap, but only with
specialists who play a champion far more than a typical player at their rank.
That would skew the benchmark upward while looking like a normal one, and it
would sit next to random samples for other champions as if they were alike.
Mastery also can't show role, and these three are often played outside the jungle.

"No benchmark" is the honest answer. The coach must never invent a number, and a
number from an unrepresentative group would be close to that.

**Cost:** the player's two most-played jungle champions have no champion-level
benchmark. The all-champion benchmark still covers those games. Viego and Nunu
have one in both cohorts. Quinn has 20 and 28 games, so it doesn't.

## Benchmarks cover the last 28 days

**Decision:** the pull lists matches from the last 28 days, about two patches.
All-champion comparisons use the player's games on the same patches. Champion
comparisons use all the player's games on that champion, with a note.

**Why:** only 30 of the player's 85 jungle games are from 16.19 on, with 4 on
Dr. Mundo and 1 on Zaahen. Matching patches at champion level would leave under
10 games on every champion.

**Cost:** champion comparisons mix patches on the player's side.

## Benchmark data lives in its own schema

**Decision:** benchmark games are in a `benchmark` Postgres schema with the same
tables as `public`, reached through an engine whose search_path is `benchmark`.

**Why:** the parser and stats run unchanged on both sides, so a comparison can't
differ because of different code. A separate engine also means a benchmark pull
has no connection to the player's tables. Matches the player appeared in are
skipped, and the player is never a seed.

**Limit:** a player's tier is checked when they join the sample, so it's their
current rank, not their rank when the match was played.

## The benchmark win rate runs a little under 50%, and we keep the sample

**Decision:** the sample stays as pulled, with no reweighting. The all-champion
sets win 48.0% in Silver and 44.6% in Emerald. A benchmark's win rate is not
read as a target: Silver's is read against 50%, and Emerald's isn't compared.

**Why it isn't a bug:** every match should give 50%, because each has one winner.
All 58,350 participants in the raw responses come to exactly 50.00%, and the
code that picks a jungler never reads the result.

**Why it's low:**
- With errors clustered on the seed player, 50% is inside the 95% range for
  Silver's set (43.5% to 52.5%). Emerald's set just misses it (40.1% to 49.1%).
- Most of Emerald's gap comes from which matches were checked first. The hash
  pick, before any rank filter, wins 46.8% on the 759 rank-checked matches behind
  this set, and 50.4% on all 2,932.
- About 1 point comes from the rank filter. Current rank partly reflects results:
  junglers below the cohort's tier win 37% to 41%, and those above win 54% to 57%.
- It isn't the second pick (48.3%), which is close to the first (48.2%). The
  target-champion rows outside the overall set run high, not low, at 53% to 58%.
- Not explained: seed players win 47.4% over 2,921 Silver games, but 49.6% in
  Emerald. Their rank at the time of each match is unknown, so this stays open.

**Why it's safe to use:** a tilt towards losses could only matter through stats
that move with winning. Weighting wins and losses equally shifts Emerald's gold
by 6, 18 and 39 at 10, 15 and 20 minutes, against margins of ±47, ±73 and ±113.
CS per minute moves 0.05 of ±0.10, and deaths per game 0.16 of ±0.30. Silver
moves less. Emerald's stats lean slightly towards losing games, within margin.

## No "first gank" stat; `first_lane_kill` instead

**Decision:** there is no first gank stat. `first_lane_kill` reports the
player's first kill or assist on an enemy laner standing in their own lane,
before 15:00.

**Why:** Riot has no gank event, and failed attempts are invisible. The timeline
records kills exactly, but positions only once a minute. In 40 of 82 jungle
games the jungler was near a lane at a minute mark before their first kill or
death, and that could be a failed gank, a farm route or walking past. Asking
whether a gank led to a kill is also circular when kills are how ganks are found.

Estimating attempts would produce numbers that look exact but are guesses. The
LLM can't tell the two apart and would present them to the user as facts, which
breaks the rule that every number comes from a tool that actually measured it.

**Limits:** a game in the `none` row doesn't mean the player never ganked, and
this stat says nothing about ganks that failed.

## Lane zones were checked against Riot's own positions

**Decision:** `first_lane_kill` splits the map into base, top, mid, bot and
jungle by coordinates, with top and bot as mirror images.

**Why:** the first hand-drawn zones were wrong, which showed up when plotted:
437 top-lane plates landed in the jungle, and the base corners counted as lanes.

**Checked against:** building events carry Riot's `laneType`. All 12 outer and
inner turrets land in the right lane, and of 5,410 plates none lands in a wrong
lane (1,032 are on base turrets and land in `base`). Deaths before 10:00 land in
the victim's lane 84% of the time for mid and 95% to 98% for top, bot and
support. The rest are mostly roams and the edges of a zone.

**Limits:** the zones were redrawn after looking at this same data, so this isn't
a blind test. A kill just outside a zone is missed rather than mislabelled.

## Ward stats leave out UNDEFINED and Teemo mushrooms

**Decision:** `wards_per_minute` ignores `WARD_PLACED` and `WARD_KILL` events
with `wardType` of `UNDEFINED` or `TEEMO_MUSHROOM`.

**Why:** `UNDEFINED` events make up about half of all `WARD_PLACED` events and
come mostly from champions like Warwick, Shen and Yorick, so they aren't ordinary
wards. Unfiltered, the player's total was 2,504 placed against Riot's own 496.

**Checked against:** Riot's end-of-game `wardsPlaced` and `wardsKilled`. With the
filter, wards placed match for this player in all 96 games and in 958 of 960
player rows. Wards destroyed match in all 960.

## Objectives with killerTeamId 300 count for neither team

**Decision:** objective stats keep only events with `killerTeamId` 100 or 200.

**Why:** 300 means neither team took the objective: 7 heralds and 3 void grubs in
this data. These events have no killer, and a "not my team, so the enemy's" rule
would hand them to the enemy.

**Checked against:** the remaining events match Riot's `teams[].objectives`
exactly for dragons, barons, heralds and grubs, in every match.
