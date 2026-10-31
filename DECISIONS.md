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

**Decision:** when building a benchmark group for `lane_diff`, leave out any
game where two players in the list are lane opponents.

**Why:** stats pool the listed players' games. If two listed players face each
other, one's +500 and the other's -500 cancel to 0, which pulls the benchmark
towards zero and hides the gap it's meant to measure. They would also count as
2 games, overstating the sample size.

**Not built yet:** `lane_diff` doesn't filter these out today, which is correct
for a single player but not for a group.

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
