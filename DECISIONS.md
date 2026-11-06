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
Medians, deaths per 10 minutes and objective share have no margin, so `clear_gap` is
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

## Vision is judged on control wards and wards destroyed, not wards placed

**Decision:** wards placed is split into control wards and trinket wards. The
vision theme judges only control wards placed and wards destroyed per minute.
Trinket wards, the share of games ending with Oracle Lens, and Riot's vision
score per minute are shown as context: their comparison rows are marked
`context_only` and get no `clear_gap`, so they can never make or support a
finding.

**Why:** the first version judged vision on all wards placed, and called it a
finding that the player was behind Silver: 0.119 wards a minute against 0.252.
That finding measured trinket choice, not vision. Trinket wards are most wards
placed, and a jungler who swaps to Oracle Lens stops placing them. Split by type,
over the 30 jungle games and 500 games per cohort on patches 16.19 to 16.21:

| Per minute | Silver | Emerald | Player |
|---|---|---|---|
| Trinket wards placed | 0.224 | 0.139 | 0.051 |
| Control wards placed | 0.026 | 0.039 | 0.060 |
| Wards destroyed | 0.083 | 0.128 | 0.126 |
| Games ending with Oracle Lens | 41% | 72% | 90% |

(Totals over all minutes, from the check below. The stat itself averages per
game, so its numbers differ slightly.) Emerald junglers place fewer wards than
Silver because most of them swap to Oracle Lens, and they make up for it with
control wards and clearing. The player does the same, more so. Judged on control
wards and wards destroyed, vision against Silver turns from a finding behind into
a finding ahead.

Vision score isn't judged either: it's Riot's own number and its formula isn't
public, so a gap in it can't be explained. The player's is a little lower than
both cohorts' (0.79 a minute against 0.85 and 0.88), shown as context only.

**How it was caught:** a sanity check on the benchmarks, not on the player.
Emerald junglers placed fewer wards a minute (0.185) than Silver ones (0.252),
the opposite of what a higher rank should show. Counting was ruled out first: our
filtered count matched Riot's end-of-game `wardsPlaced` in all 500 Emerald games,
497 of 500 Silver games and all 30 of the player's. Splitting by `wardType` and
reading the trinket slot (`item6`) from the stored raw match responses showed
where the gap was.

**Limits:** the trinket is read at the end of the game, so a mid-game swap isn't
seen. Oracle Lens share is a plain percentage of games, with no margin.

## Objectives with killerTeamId 300 count for neither team

**Decision:** objective stats keep only events with `killerTeamId` 100 or 200.

**Why:** 300 means neither team took the objective: 7 heralds and 3 void grubs in
this data. These events have no killer, and a "not my team, so the enemy's" rule
would hand them to the enemy.

**Checked against:** the remaining events match Riot's `teams[].objectives`
exactly for dragons, barons, heralds and grubs, in every match.

## A clear gap isn't a finding on its own

**Decision:** `compare` groups rows into five themes: economy, vision, deaths,
fights and objectives. A theme gives a finding when two different metrics are
clear in the same direction, or when one gap is at least 2 times its combined
margin. The coach's prompt treats only these as findings. Any other clear row is
`worth_watching`, and the coach has to say it may be chance. The rule is in
`benchmarks/themes.py`, and the 2 is `STRONG_GAP_MULTIPLE` in `compare.py`.

**Why:** Silver's all-champion comparison has 32 rows with a margin. At a 95%
margin, about 1 in 20 can look clear by chance, so one row proves little. The
rule is in code because a rule that's only in a prompt can't be tested.

**Why 2 times:** a clear gap sits about 2 standard errors from zero, and twice the
margin sits about 4. Chance gives that about 1 time in 10,000, so a lone gap that
size stands by itself. Wards placed against Silver, -0.133 ±0.033, is the case
that prompted it. It's a round number, not a fitted one.

**What counts as a second metric:** the same metric at another minute doesn't,
because gold at 20 includes gold at 10. Deaths in different phases do, because
those windows don't overlap. Gold and CS share the economy theme because they move
together, but they still count as different metrics, so economy reaches a finding
more easily than the others. Silver and Emerald compare against the same games
from the player, so agreement between them isn't counted at all.

**Left out:** rows split by win or loss, and rows on fewer than 10 of the player's
games.

**Limits:** objective share has no margin, so that theme can't give a finding.
Win rate's margin uses the normal approximation, which is rough near 0% and 100%
and on small samples. Win rate is in no theme, because it's a result, not a cause.

## The coach's numbers are checked in code

**Decision:** after each reply, `agent/numbers.py` looks for every number in that
conversation's tool results. A miss gets one retry that names the numbers. If the
next reply also fails, it's shown with a warning and the status `unverified`.

**Why:** "the LLM never computes a number" can't rest on a prompt. Opus 5.5 also
rejects forced `tool_choice`, so the API can't require a tool call. A reply that
skipped the tools has no results behind it, so this check catches that too.

**Exemptions:** only list numbering and the phrase "1 in 20". Allowing small
numbers would be simpler, but it would let a made-up "3 deaths" through. A harmless
"top 3" costs one retry instead.

**Limits:** it proves a number exists in a result, not that it's attached to the
right stat. It can't read numbers written as words, such as "twice". The eval has
to cover both.

**Tool descriptions count as a source.** The first eval run caught the coach
quoting "25:00", the start of the late game, which is in the deaths tool's
description but in no result. Descriptions hold fixed facts we wrote, so their
numbers are allowed. The cost: an answer that skipped every tool can now use the
few numbers in descriptions, such as 10, 15, 20, 25 and 60, without being caught.

## The eval's grader passed calibration but was often wrong live

**What happened:** the grader agreed with the calibration labels on 44 of 46
replies (96%), above the 90% bar. In the first live run on Opus, it then gave 12
failures, and 5 of those were the grader's or the eval's own mistakes: about 4 in
10, against the 1 in 10 an eval can tolerate.

**Why:** the calibration examples were too clear-cut. Each planted one obvious
error into a reply graded against the full comparison. Live replies were harder
in ways the examples never tested:
- The coach asked for one theme only, so the economy finding's rows weren't in
  the results, and the grader called a real finding unsupported.
- A number's meaning came from a tool's description ("at minute 10"), which the
  grader never saw.
- Vague words such as "several" or "much further" were read as numbers in words.
- Grouping two findings against an area with no gap was read as ranking them.
- The Dr. Mundo phrase check was code, and missed "no Silver benchmark exists".

**Decision:** the grader now sees each tool's description, finding summaries
include `clear_gap`, and the rubrics cover these cases. The calibration set adds
the honest version of each case the grader got wrong, graded against the same
kind of tool results the live run had, so a regression shows up there first.

**Result:** the second calibration agreed on 62 of 62. In the second live run, 1
of the 3 failures was still the grader's: the coach quoted phase boundaries from
a tool it hadn't called, and the grader only sees the descriptions of tools that
were called. Three failures is too few to measure a rate.

The grader now sees every tool's description, and the calibration has a reply
quoting a boundary from an uncalled tool. The third calibration agreed on 65 of 66.
The miss was a reply the grader judged both ways across two passes: "farm and
vision are where you'll gain the most". On that wording the grader is unstable,
so a failure there needs reading by hand.

**Lesson:** a high calibration score on easy examples says little. Calibration has
to include the hard, honest answers a grader is likely to fail, not just obvious
planted errors. Reading every live failure by hand is what found this.

## The coach never ranks findings in different units

**Decision:** the prompt says gaps in different units can't be ranked, so asked for
a weakest area, the coach says so and lists the findings. Win-only and loss-only
rows are always a suggestion, never a fact, and only a theme the tool marks as a
finding may be called one.

**Why:** the first eval run caught all three. Three replies ranked CS against
wards ("the biggest issue", "your weakest area is economy"), one stated a win-only
pattern as fact, and one put a row from another tool under a finding's heading.
CS per minute and wards per minute have no common scale, so any ranking is the
model's opinion presented as data.

## The demo replaces every player's identity, including mine

**Decision:** the demo ships 12 of my jungle games, the most recent ones rather
than hand-picked. Every PUUID, Riot ID, summoner name and ID, match ID and game ID
is replaced, I become DemoJungler#DEMO, profile icons and levels are made the
same for everyone, and real dates are shifted by one fixed amount. There's no
benchmark in the demo.

**Why me as well:** with my real Riot ID left in, anyone could open my public
match history, find these games, and read the other players' real names, which
undoes the rest.

**Why fields are rewritten by name everywhere:** Riot repeats identities in
unexpected places, such as the game ID inside the timeline's GAME_END event. The
export then searches the output for every original value and writes nothing if
one is left. On the first export it stopped on 269 hits: a player's name that is
also a champion name. Champion names are exempt, because the word appears as the
champion, not the player.

**Why 12 games:** every stat needs 10 games before it says anything. With 5,
every number in the demo would be flagged.

**Limit:** stats and champions are kept, so someone who already knows my Riot ID
could match these games by their stats. The benchmark stays out because it is
1,271 other players' games.

## The number check and the model grader are both needed

**Decision:** the eval keeps both kinds of check: code for what can be checked
exactly (every number comes from a tool, a tool was called, a required phrase is
there), and a model grader for what a sentence claims about those numbers.
Neither replaces the other.

**Why:** the local model, `qwen3:4b`, made this concrete. All 5 of its answers
passed the number check, and three of them were wrong:
- "you destroy fewer wards", when the data says more;
- Silver's 19 games given as the player's;
- gold at minute 10 called "gold per minute".

Every number was real, so the number check passed them. What was false was the
direction, the owner or the unit around the number. The Haiku grader failed all
three. Opus rarely makes these mistakes, so its runs never showed the gap. A weaker
model did.

**Trade-off:** the grader is a model and can be wrong too, which is why it's
calibrated against replies with known verdicts before a run is trusted. The number
check is exact but narrow. It proves a number exists in the tool results, not that
the sentence around it is true.

**The local model itself:** it stays as a free option, labelled "several minutes
per answer and less reliable". On a 4 GB GPU, the 32,768-token context a full
comparison needs runs mostly on the CPU: answers took 4½ to 16 minutes, and 3 of 8
questions didn't finish. The 600-second limit per call stays, so a stuck call fails
instead of hanging the page.

## Champion select shows options, reads only champions, and never picks

**Decision:** the Draft page and the `draft_board` tool take only the champions
on screen in champion select: picks on both teams and bans, typed in by the
player. Nothing is read from the game client, and no other player's name, rank
or history goes in. They show what the team lacks and which of the player's own
champions fill it, and never say which one to pick or rank them.

**Policy, checked on Riot's developer portal on 2026-11-04:**

- [General Policies](https://developer.riotgames.com/policies/general), Game
  Integrity (last updated May 29, 2025): "Products cannot de-anonymize players
  who cannot reasonably be identified from visible information."
- [League of Legends docs](https://developer.riotgames.com/docs/lol), Developer
  API Policy, Game Integrity: "Products cannot identify or analyze players who
  are deliberately hidden by the game." Ranked solo/duo champion select hides
  the other players' names, so this rules out looking them up.
- The same page, Game Policy, Examples of Unapproved Use Cases: "Apps that
  dictate player decisions." This is why the helper shows and doesn't pick. It
  also lists "Products may not provide any game-session-specific information
  that would be previously unknown to the player."
- The same page, Examples of Approved Use Cases for Personal Keys: "Game
  overlays that provide static data that is available prior to the game" and
  "Aggregate player stats (no specific players)". The gap rules use the first
  kind of data, and the pool shows the player's own stats.

**Not verified on Riot's own pages:** the rule written specifically for
champion select, from patch 12.22: "Apps that reveal player names or stats in
Champ Select will be asked to remove this feature immediately. This
specifically applies only to Ranked Solo/Duo". I found it only in a
[repost of Riot's announcement](https://devtrackers.gg/leagueoflegends/p/749a443a-apps-that-reveal-player-names-or-stats-in-champ-select-need-to-remove-these-informations-starting-patch-12-22).
Riot's League policy article on its developer support site
(support-developer.riotgames.com, article 22698698001939) is behind a bot
check that automated tools can't pass, so it wasn't read. The design already
meets the stricter reading, because no other player's name or stats are used at
all, in any queue.

**Manual entry, not the client:** the client's champion-select session carries
player identifiers. Not reading it at all removes the risk instead of filtering
it.

## No matchup data, and none is estimated

**Decision:** every enemy pick shows "No matchup data". There is no win rate
for one champion against another, no estimate, and no general rule of thumb in
its place. The coach is told the same, and the eval's `draft` case checks it.

**Why:** a win rate within about ±10 points needs about 96 games of one exact
pair (1.96 × 0.5 / √n). Counted on 2026-11-04, a jungler's champion against each
enemy champion:

| Data | Games | Pairs | Biggest pair | Pairs with 10+ games | Pairs with 96+ games |
|---|---|---|---|---|---|
| Benchmark (Silver and Emerald) | 1,271 | 5,841 | 26 | 69 | 0 |
| My own games | — | 379 | 3 | 0 | 0 |

The benchmark pull can't close that gap. Even the most common pair would need
about 4,700 games, and typical pairs 60,000 to 120,000. At the app limit of 100
requests per 2 minutes, about 3,000 matches an hour, that's 20 to 40 hours of
pulling per rank, every two-week patch. And a jungler's win rate against, say, the enemy bot laner
mostly measures team compositions, not a matchup.

## Gaps are rules over Data Dragon's ratings

**Decision:** a team's gaps (no frontline, no magic damage, no physical damage)
are rules in `analytics/draft.py` over Data Dragon's tags and Riot's 0-10
attack and magic ratings, not stats from games. Damage type is the higher of
the two ratings, and a tie counts as both. A frontline is a Tank, or two
Fighters. A champion adds a missing piece only if the team has it once the
champion is added, so a lone Fighter doesn't add a frontline to a team with no
other Fighter. (v4 listed any Fighter, which was a bug.)

**Why ratings:** tags alone can't say which damage a champion deals, and a
table of our own would be our judgement, updated by hand. **Cost:** some
champions come out wrong. Riot rates Dr. Mundo's magic above his attack, so he
counts as magic damage.

**The pool:** jungle champions with 3 or more of the player's games, most
played first. Under 10 games the win rate reads "too early to tell".

**Data Dragon isn't the Riot API:** it's a public file CDN with no key and no
rate limit, so its requests don't go through the rate limiter. The app stores
the latest champion.json at startup, raw next to the parsed rows, once per
version. The coach's tool only reads what's stored.

## No post-game draft review

**Decision:** the Matches page shows each game's champions and stats, but no
review of the draft. A review would have shown, for each game, what the team
lacked by the Draft page's rules, whether my pick added it, and the evidence
across many games. It wasn't built because the evidence shows no clear effect,
and my own record leaves almost nothing to review.

**The evidence, counted on 2026-11-04:** the same rules over all 1,271
benchmark games, so 2,542 teams, each judged on its final five champions:

| Missing piece | Teams missing it | Teams that had it |
|---|---|---|
| No frontline | won 48.4% ± 6.2 of 252 | won 50.2% ± 2.0 of 2,290 |
| No magic damage | 30 teams, with margins of about ±25 points | the rest |
| No physical damage | none | all |

Teams without a frontline won 1.8 points less, well inside a margin of about
6.5 on the difference, so this sample can't tell whether lacking a frontline
matters. Seeing a 3-point difference would need about 1,100 teams without a
frontline, about 5,800 matches: 4½ times what's stored. Magic damage has too
few teams for any comparison, and no team ever lacked physical damage. Even
with enough games it would be a correlation, since teams without a frontline
differ in other ways too.

**My own record:** in 23 of my 85 jungle games, my four teammates had no
frontline. My pick added it in 20 of them (8 wins) and didn't in 3 (1 win).
Three games is too early to tell anything, so there's no comparison to make.
My teammates lacked magic damage in 2 games, and I added it both times.

So a review would mostly say "inside the margin", about a gap I already fill.

**What would change this:** a benchmark pull large enough for the frontline
margin to come down to about 3 points. Win rates by composition need only the
match call, not the timeline, so this is cheaper than a full pull, but still
hours of rate-limited calls.

## The enemy's composition: same rules, and advice labelled as general

**Decision:** the Draft page describes the enemy team with the same rules as
mine: each champion's damage type from Riot's attack and magic ratings, and
its tags for the frontline. The damage mix gets a label from 3 picks, when one
type is at least 3 of every 4 picked ("mostly physical: 3 of 4"); otherwise
it's "mixed". Under 3 picks, it says there are too few to call.

**General advice:** a mostly physical team gets "armour items are worth more",
and a mostly magic one "magic resistance items are worth more". It's general
game knowledge, not from my games, and it's labelled that way on the page and
in the coach's tool result. It has no item stats and no win rates, and a mixed
team gets none.

**Why 3 of 4:** it means all 3 of 3 picks, 3 of 4, or 4 of 5. A lower share would call a team "mostly physical" with
two magic champions on it.

**Matchups:** the page says "No matchup data" once, under the enemy picks,
instead of on every enemy champion.

## The matchup rule covers outcomes, not how to play

**Decision:** the coach still never says who wins a matchup, who is favoured, or
that a champion is a good pick into another, in numbers or in words, even as
general advice. It may now say how to play with or against a champion, such as
what an ability does or when to engage, when that comes from Riot's own text
(`riot_notes`) and is labelled as general knowledge, not the player's data.

**Why:** in v4 the rule banned anything about one champion against another,
which also banned "stay spread out against Lee Sin's ultimate". That's Riot's
own advice, not a guess and not a claim about who comes out ahead. The line now
sits at outcomes: those need matchup data, which doesn't exist here (see "No
matchup data, and none is estimated").

**The edge case:** Riot's text says Lee Sin "is still vulnerable to magic
damage". Quoting that passes. "So your magic damage champions do well against
him" fails: it turns Riot's tip into a claim about who wins. Both are calibration
examples.

**Checked by:** the coach prompt, the `no_matchup_claim` grader check (narrowed
to outcomes), 7 new calibration examples on a saved options board, and the
`draft_options` eval case.

## Riot's text comes from Data Dragon, and its tips can be stale

**Decision:** each champion's own Data Dragon file is stored at startup, raw
next to the parsed abilities and tips, for all 173 champions. The Draft page
shows Riot's tips for free: for playing each of your champions on its card, and
against each enemy pick. The coach gets the same text through `riot_notes`.

**Why Data Dragon, not the model's memory:** a model's memory of champion kits
can be out of date, and a new champion like Zaahen may not be in it at all.
Riot's text is versioned with the game.

**Cost:** Riot doesn't always rewrite tips when a champion changes. Dr. Mundo's
tips still name "Sadism" and "Cleavers", which his current abilities don't have.
So abilities come first, every tip is labelled as possibly older than the
abilities, and the coach is told to use a tip only if it agrees with them. Some
champions, such as Zaahen, have no tips at all.

## Options for this draft: one capped call, with its ceiling shown first

**Decision:** the "Options for this draft" button doesn't let the coach call
tools. The server runs `draft_board` and `riot_notes` itself and puts their
results in the question, and the model gets one call with no tools and at most
6,000 output tokens. The number check's one retry is the only second call.

**Why:** with tools, the coach decides how many turns to take, so the cost isn't
known until it's spent. This way it has a ceiling before anything is sent: the
input is counted exactly by Anthropic's token count, which is free, and the
output is capped. The ceiling prices every input token at the dearer of the
input and cache-write rates, and covers the retry. The page shows it, and the
person clicks a second time to send.

**On the README's board (2026-11-04):** 15,277 input tokens, so at most $0.21 on
Sonnet 5.5 (the default) or $0.42 on Opus 5.5; $0.10 and $0.20 without the
retry. The local model is free.

## The champion card: side by side, and benchmarks per champion

**Decision:** a pool champion's card shows the player's CS per minute, gold at
15, deaths in each phase and kill participation on it, next to the same stats
over all their jungle games, each with its margin and games. Under 10 games a
value is greyed and says "too early to tell". The two sides are never
subtracted: the champion's games are part of the overall average, so a
difference between them isn't a fair comparison.

**Benchmarks:** a rank's benchmark on one champion needs 30 games from 10
players, the same floors as everywhere else. Emerald's win rate on a champion
isn't shown, for the same reason as Emerald's overall win rate: Emerald players
face Emerald opponents. On 2026-11-04, only Viego and Nunu reached the floors
in both ranks; Dr. Mundo, the most played, had 19 Silver games and 10 Emerald.

**The Dr. Mundo pull:** Riot can't list matches by champion, so the pull checks
more random cohort matches, and he turns up in about 0.6% of Silver matches and
0.3% of Emerald ones. Overnight on 2026-11-04, Silver went from 3,000 to 5,000
checked matches, and Dr. Mundo from 19 games to 32 from 29 players: his Silver
benchmark now exists. The Emerald pull stopped overnight when Docker did, and
finished on 2026-11-06: 3,000 to 9,000 checked matches, and Dr. Mundo from 10
games to 37 from 35 players, so his Emerald benchmark exists too.

## Auto-sync every 30 minutes, even during a benchmark pull

**Decision:** while the API runs, every tracked player is synced every 30
minutes through the same `sync_player` as a manual sync, the first round a
minute after startup. A round skips while a manual sync runs, and stops at a
refused key; every page then warns that the key needs replacing.

**Why it may run during a pull:** a manual sync and a pull still can't run
together, because a full sync takes minutes of the shared call budget. An
auto-sync round is small: about 4 calls for a player with no new games, plus 2
per new game. The rate limiter is shared and reserves each call's slot with no
wait between checking and reserving, so concurrent callers can't overrun Riot's
limits; the pull only slows by those few calls. Skipping rounds during a pull
would have meant no new games for the 5 or more hours a pull can take.

**Limits:** nothing syncs while the computer sleeps or Docker is closed, and a
development key still expires every 24 hours, after which auto-sync waits for
a new one.

## Benchmarks on demand, for any rank and role

**Decision:** a cohort is one rank and one role, and its name says which:
`gold_middle` is Gold mid laners. Silver and Emerald junglers keep their names.
A cohort exists once its sample has rows; there's no table of cohorts to keep in
step with the data. Each player gets their peers' cohort in their main role and
in every role with 10+ games. Outside the jungle there are peers only; Emerald
stays a target for junglers. When a cohort has no benchmark, the Overview offers
a pull with its time, which stops at 500 games. "Pull more" checks 2,000 more
matches for champion benchmarks.

**Same rules as before:** 500 games, 30 games and 10 players before a benchmark
exists, one player per match per cohort, 28 days, at most 10 games per player
per champion, nothing substituted. The targets for champion benchmarks are the
champions the requesting player has 5+ games on in that role.

**The estimate comes from measured pulls.** The Gold mid pull, the first made
from the Overview's offer, sampled 500 games from 653 checked matches in 29
minutes, so 500 games are offered as about 653 matches and 29 minutes. I first
used the Silver jungle pull, 683 matches in 91 minutes, but it ran beside the
Emerald pull and shared its call budget, so it was three times too slow. Past 500, only target
champions are rank-checked; the Emerald Dr. Mundo pull checked 3,584 matches in
75 minutes, so "Pull more" is about 42 minutes.

**Stored lobbies are reused, but not counted on.** A new cohort first queues
the stored matches of other cohorts at the same rank still inside the window:
they are lobbies of that rank, and checking them costs no match call. That
should be faster, but no pull has measured it, so the estimate assumes the
fresh rate.

**Master and above can't be pulled yet.** The pull finds players on Riot's
divided ladder, which stops at Diamond; the apex leagues are behind other
endpoints.

**Tested on a real player:** a random Gold mid laner from the ladder, picked by
9 of their last 10 ranked games being mid. Their Riot ID stays out of the docs
and screenshots. Their 100 synced games are 38 mid, 28 bot, 22 top and 12
jungle, so they get four roles. The Gold mid pull reached 500 games from 455
players. 76% of checked matches gave a game, against 73% for Silver junglers.

## Each role is judged on its own measures

**Decision:** a comparison uses the cohort's role and that role's measures.
"Judged" measures can make a finding; "context" ones are shown beside the
benchmark and never judged.

| Role | Judged | Context |
|---|---|---|
| Jungle | Unchanged | Unchanged |
| Top | Gold and CS, lane difference, deaths, kill participation, vision, solo kills, lane plates | Damage share, plates last hit |
| Mid | Gold and CS, lane difference, deaths, kill participation, vision, damage share | Roams |
| Bot | Gold and CS, lane difference, deaths, vision, lane plates | Kill participation, plates last hit |
| Support | Deaths, kill participation, all wards placed, control wards, wards destroyed | Gold, CS and lane difference |

Objective share stays jungle-only: for other roles it measures the team. First
lane kill stays jungle-only: it measures ganks.

**Counted by us, not taken from Riot.** Match responses carry Riot's own
"challenges" numbers, such as `soloKills` and `turretPlatesTaken`, but their
formulas aren't public, like vision score's. Solo kills are counted from the
timeline as kills with no assisting player. Damage share is the player's share
of their team's damage to champions, from Riot's end-of-game totals.

**Plates before 14:00 only.** Our stored timelines show plates falling all game:
up to 15 per lane per team across 203 matches, the latest at 48 minutes. Counted
over a whole game, they would mostly measure late pushing. Before 14:00 they
measure the lane. Minions take many plates, so plates the player last-hit are
context, and the judged number is every enemy plate that fell in their lane.

**Support vision counts every ward.** A support's wards include the support
item's (`SIGHT_WARD`, 3,975 in our stored games), so all placed wards are judged
for supports. Other roles still judge only control wards and wards destroyed,
because trinket wards mostly show trinket choice.

**Deaths before objectives aren't in the support comparison.** I planned them,
but the stat compares rates against a baseline and has no margin, so it could
never be judged. The coach can still use it.

**A theme with only context rows says so** ("context_only"), instead of "no
verdict yet", which would suggest a verdict was coming.

**Checked against the jungle:** every row and theme of four jungle comparisons
(Silver and Emerald, all champions and one champion) is identical to before.
Only the vision note's wording changed, from "a jungler" to "a player".

## With no benchmark, the Overview shows the player's own numbers

**Decision:** when no cohort fits a player in a role, the Overview says why,
offers the pull, and shows the role's measures from the player's own games:
over all games, and over wins and losses apart, each with its margin and sample
size. Win rate isn't split, because split by result it says nothing.

**Why wins against losses:** it's the only comparison that needs no one else's
games, so it can't stand in for a benchmark or borrow another rank's. It goes
through the same gap and margin code as a benchmark comparison, and a
difference is only called clear with 10+ games on each side. It shows how a
measure moves with the result, not what caused it, and the page says so.

**Never a number from memory.** The page doesn't say what "a typical Gold mid
laner" does: without a pulled cohort, there's no such number to show.

## The Draft pool in any role

**Decision:** the Draft page has a role tab for each role the player gets
benchmarks in, their main role first and chosen by default. The pool is their
champions with 3+ games in that role, and a champion's card puts its games
beside the player's average in that role, with that role's cohorts as
benchmarks. The gap rules and the enemy composition don't depend on role, so
they're unchanged. The `draft_board` tool takes an optional `role`; with none,
it uses the player's main role.

## The coach works in any role

**Decision:** the coach is no longer a jungle coach. Tools measured in one role
take a `role`, and a null role means the player's main role, not jungle: before
this, a mid laner asking about kill participation would have been given their
jungle games. `compare_to_benchmark` takes any cohort name and checks it in
code, because a fixed list can't hold cohorts pulled on demand. `data_coverage`
lists the player's roles and every cohort that could fit them. New tools:
`role_measures` (solo kills, lane plates, damage share and roams in one tool)
and `wins_and_losses` for a role with no benchmark, which the prompt says to present as how a measure moves with the
result, never as a finding. Objective share, first lane kill and farm by stretch
stay jungle-only, and their descriptions say so.

**The eval gets a mid laner, asked as "you".** The new `mid_peers` case asks the
test Gold mid laner "What should I work on in my mid games?" and passes its code
check only if every benchmark comparison uses their own peer cohort. The case
picks its player by rule (the first synced player whose main role isn't jungle)
and shows them to the coach as the owner with a placeholder name, so no Riot ID
reaches the prompt or the saved results.

**Four stats, one tool.** Anthropic's API refuses a request with more than 20
strict tools, and four separate tools would have made 23: the first eval run
was refused before the model answered, at no cost. Strict mode stays on every
tool, so the API keeps enforcing each schema, and a test now fails above 20.

**"MAIN" instead of a nullable role.** Strict tools may also have at most 16
parameters with union types in all, and the nullable roles made 22: the second
run was refused too, also at no cost. A role measured in one role is now a plain
choice that includes "MAIN", the player's main role, which brings the count to
15. Code that calls a tool without a role, such as the API's stats endpoint,
gets MAIN filled in. A test fails above 16.

## Every number cites the field it came from

**Decision:** on Claude models, the server gives every object in a tool result
a `ref` (the call's number in the conversation, then the object's place in the
result, such as `2.14`), and the coach writes each number followed by
`[[ref.field]]`, or `[[tool_name]]` for a fixed fact in a tool's description.
Code checks that the number equals that field exactly, with no rounding, and
fails any uncited number. One retry names each problem, then the reply is shown
with a warning, as before. The markers are removed before the reply is shown,
and each cited number comes back as a link whose hover shows its source.

**Why refs, not paths:** a path such as `rows/14/my_value` makes the model count
rows in a result of up to 32,000 characters. A ref is copied, not counted.

**What's exempt:** list numbering, "1 in 20", digits in the player's Riot ID,
and minute labels ("at minute 15", "15 minutes", "the 10-minute mark", "15:00").
A minute label must still be a minute the results define: a `minute` field, a
stretch boundary, a game time in a tool's description, or minute 0, the start
of the game. The first `mundo` run failed only on minute labels the coach
wouldn't cite, and a minute can't make up a stat.

**Percentages:** every percent field already holds a percent (52.9, not
0.529), so nothing is converted. If a tool ever returns a fraction, the percent
gets its own field in SQL: multiplying by 100 would be a calculation.

**The local model keeps the plain check.** A 4B model can't be relied on to
cite, so it still checks that each number appears somewhere in the results.

**What it catches, by replaying the recorded errors (free):** "±25" from 24.5
and 24.7 is caught when it cites the margin it rounded. It passes only if it
cites Viego's 25.0% win rate, and the hover then shows "Viego, win rate".
`mundo`'s "8 or fewer games each" is caught only if it cites the wins' 9; cited
to the losses' 8, it passes, because the error is the word "each", not the
number.

**Measured on Opus 5.5:** `draft` passed first time with 10 citations ($0.08).
`mundo` first failed on minute labels; with them exempt, it passed every check
with 31 citations after one retry ($0.19).

**The grader sees the citations.** Each graded reply's citations are added to
what the grader reads, so its wrong-stat check sees which field each number came
from. The grader's calibration examples don't include citations.

## The Compare page and stretches in any role

**Decision:** the Compare page has the Overview's role tabs and compares each
role with its own cohorts: peers, and for junglers below Emerald, Emerald as a
target. Its two slots are now "peers" and "target", named by rank, instead of
Silver and Emerald. Farm by stretch takes a role and measures against the lane
opponent, the enemy player in the same position, and each of the role's
cohorts. Switching player clears the page first, so one player's comparisons
never show under another's name.
