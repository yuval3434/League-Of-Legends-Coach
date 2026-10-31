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
