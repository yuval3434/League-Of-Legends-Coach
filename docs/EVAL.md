# Eval history

Every eval run, oldest first, with what it found and what was changed after it.
The [README](../README.md#eval) says how the eval works and sums up the latest
results.

## Results on Opus 5.5

The first run found real coach failures, such as ranking CS against wards as "the
biggest gap", and also grader mistakes. After fixing both, the same 8 questions:

| Check | How | First run | After fixes | Wards split |
|---|---|---|---|---|
| The number check passed | Code | 7 / 8 | 8 / 8 | 8 / 8 |
| A tool was called | Code | 8 / 8 | 8 / 8 | 8 / 8 |
| Says "no benchmark" or "not enough data" | Code | 1 / 2 | 2 / 2 | 2 / 2 |
| Numbers in words | Code, then model | 6 / 8 | 8 / 8 | 7 / 8 |
| Ranking gaps in different units | Model | 1 / 4 | 4 / 4 | 4 / 4 |
| Win-only or loss-only rows as findings | Model | 1 / 3 | 3 / 3 | 2 / 3 |
| A real number on the wrong stat | Model | 7 / 8 | 7 / 8 | 8 / 8 |
| Claims the tools don't support | Model | 6 / 8 | 6 / 8 | 8 / 8 |
| Presents both Silver findings | Model | 1 / 1 | 1 / 1 | 1 / 1 |
| No relative stats compared against Emerald | Model | 1 / 1 | 1 / 1 | 0 / 1 |
| **Total** | | **39 / 51** | **48 / 51** | **48 / 51** |

Each run cost about $0.85. The grader's rubrics changed between the runs too, so
not all of the gain is the coach's. Two of the three remaining failures led to
small fixes, a prompt line and a grader input, that haven't been through a live
run yet.

The third run followed the wards split (see DECISIONS.md), which turned vision
from a finding behind Silver into one ahead, so its answers aren't the same test as
before. Its one Emerald failure is a grader mistake: the reply refused gold
difference against Emerald and compared only gold and CS at each minute, which
are allowed. The other two are the coach's: a win-only row stated as fact, and
"your one weak area". It cost $0.91.

## The full run on v8

v8 changed the prompt from a jungle coach's to one for any role, and changed the
tools, so all 12 cases were run again on Opus 5.5 on 2026-11-06. Every answer
passed the number check and called tools. It cost $1.68: $1.56 for the coach
and $0.12 for the grader.

| Check | How | Passed |
|---|---|---|
| The number check passed | Code | 12 / 12 |
| A tool was called | Code | 12 / 12 |
| Says the expected words | Code | 5 / 5 |
| No number the retry had to fix | Code | 1 / 1 |
| Compared with the player's own peer cohort | Code | 1 / 1 |
| Claims the tools don't support | Model | 12 / 12 |
| Ranking gaps in different units | Model | 5 / 5 |
| Win-only or loss-only rows as findings | Model | 3 / 3 |
| Presents both Silver findings | Model | 1 / 1 |
| No relative stats compared against Emerald | Model | 1 / 1 |
| No pick chosen | Model | 2 / 2 |
| A real number on the wrong stat | Model | 11 / 12 |
| Numbers in words | Code, then model | 10 / 12 |
| No matchup claim | Model | 1 / 2 |
| Nothing computed between minutes | Model | 0 / 1 |
| **Total** | | **77 / 82** |

Reading the five failures against the replies and tool results, two are the
coach's and three are the grader's:

- **Coach, `mundo`:** it said the win and loss splits had "8 or fewer" games
  each, when the wins had 9 at minutes 10 and 15. The number check missed it
  because 8 is in the results too, as the losses' count.
- **Coach, `stretch_no_tool`:** it correctly refused to give the gold lost from
  10 to 15, then said "the gap grows faster in games you lose". That compares
  the change from 10 to 15 in losses with the change in wins, a subtraction no
  tool made, in words instead of a number.
- **Grader, `stretch_no_tool`:** "here are the two numbers" counts the reply's
  own table rows, not anything in the player's data.
- **Grader, `draft`:** "fewer than two Fighters" is copied from the tool's own
  rule text.
- **Grader, `draft_options`:** it failed Amumu's strengths ("his E reduces the
  physical damage he takes, and three of the four enemies are physical") as
  implying a good pick. The case asks for each champion's strengths against the
  enemy team from Riot's text, and the matchup rule covers only outcomes: who
  wins, who's favoured, who's a good pick. The reply makes none of those and
  says so.

That reading is mine; the table keeps the grader's verdicts. The two coach
failures aren't fixed: they're more cases of two known gaps, listed under the
limits below.

## The full run with citations

The first run with number citations, on 2026-11-07: all 16 cases on Opus 5.5,
with four new cases outside the jungle. It cost $2.72: $2.56 for the coach and
$0.16 for the grader. 12 of the 16 replies needed a citation retry, which is
most of why it cost more than v8's $1.68.

| Check | How | Passed |
|---|---|---|
| A tool was called | Code | 16 / 16 |
| The number check passed | Code | 15 / 16 |
| Role-taking tools used the role asked about | Code | 4 / 4 |
| Compared with the player's own peer cohort | Code | 1 / 1 |
| Never says "enemy jungler" about mid lane | Code | 1 / 1 |
| Says the expected words | Code | 5 / 7 |
| No number the retry had to fix | Code | 0 / 1 |
| A real number on the wrong stat | Model | 16 / 16 |
| Numbers in words | Code, then model | 15 / 16 |
| Claims the tools don't support | Model | 14 / 16 |
| Win-only or loss-only rows as findings | Model | 2 / 5 |
| Ranking gaps in different units | Model | 5 / 5 |
| Nothing computed between minutes | Model | 3 / 3 |
| No pick chosen | Model | 2 / 2 |
| No matchup claim | Model | 1 / 2 |
| Presents both Silver findings | Model | 1 / 1 |
| No relative stats compared against Emerald | Model | 1 / 1 |
| **Total** | | **102 / 113** |

Reading each of the 11 failures against the replies and tool results: four are
the coach's, three the grader's, and four were problems in my checks or cases.

- **Coach, `bot_no_benchmark`:** it said none of the stretch gaps was beyond its
  margin, then made "the 15–20 minute stretch" the first thing to work on.
- **Coach, `wins`, twice:** it stated "getting ahead helps you win" as a fact,
  presented lane differences split by result as facts, and built a weakness on
  mid-game deaths per 10 minutes, a row with no margin.
- **Coach, `draft_options`:** "one gap" and "two physical ranged carries" are
  counts from the board written as words.
- **Grader, `bot_no_benchmark` and `support_vision`:** both failed the
  wins-and-losses check for differences that `wins_and_losses` marks clear
  (early deaths 2.09 in 11 wins against 3.71 in 17 losses; the support's deaths
  in all three phases), stated as links, not causes. That check was written for
  rows split by result inside a comparison, which are only ever a suggestion;
  the v8 tool reports clear differences between wins and losses on purpose.
- **Grader, `draft_options`:** "effective against tanks such as Darius and
  Malphite" applies Riot's tip to the board: how to play, not who wins.
- **My checks, `farming`:** the citation check didn't read "20:00:" at the end
  of a bold heading as a time, so it failed "20" and "00" twice. Fixed.
- **My check, `stretch_no_tool`:** the first reply left a minute range without
  the word "minute", which my minute pattern doesn't cover; the retry fixed it.
  The check is meant to catch a computed number on the first try, and a
  citation slip now fails it too.
- **My case, `bot_no_benchmark`:** the reply said "no Gold bot lane benchmark",
  and my pattern allowed only two words between "no" and "benchmark". Fixed.
- **My case, `mundo`:** it expects "no benchmark", but Dr. Mundo has had a
  Silver benchmark since the overnight pulls (32 games from 29 players), so the
  coach rightly compared with it.

Two of the four new cases passed every check (`top_lane`, `mid_stretch`), and
every role-taking call used the role the question named.

**After the fixes**, on 2026-11-08. The prompt now says never to pick a gap
without a verdict as something to work on. The grader's wins-and-losses check
now passes a difference that `wins_and_losses` marks clear, when it's stated as
a link and not a cause. `mundo` now checks the coach compared with Silver on Dr.
Mundo. `first_try` now fails only on a number found in no tool result.

- **Calibration:** with three new examples from a real support's result, the
  grader agreed on all 108 gradings ($0.15).
- **`bot_no_benchmark`, `wins` and `mundo` re-run on Opus 5.5** ($0.48):
  `bot_no_benchmark` and `mundo` passed every check, and the coach failures from
  the full run were gone.
- **`wins` failed two checks:**
  - **Coach:** it gave the dragon samples as "177 vs 54", then corrected itself
    to 227 later in the reply. The 54 is the Baron losses sample, cited
    correctly to that field: another case of the right-field, wrong-sentence
    limit below.
  - **Grader:** it read the minute-20 differences as not clear. The rows mark
    them clear, but the citations pointed at each row's wins and losses sides,
    which don't carry the flag.
- **A fix not yet re-run:** both `wins` failures came partly from how a
  citation to a nested object was labelled: "value 16.7 → sample", with no sign
  it was Barons, losses. Labels now name the row and side ("objective
  BARON_NASHOR, losses → sample"), for the hover and for the grader. No re-run
  has tested the fixed labels yet.

## Newer cases

Two cases were added after those runs. Each has been run once on Opus 5.5:

- **`stretch_no_tool`** asks for the gold lost between minutes 10 and 15, with
  the stretch tool removed. The only way to an answer is then to subtract two
  minutes' gaps: 461 − 219 = 242, while the real figure is 234. The coach must
  say it doesn't have the number. A code check also fails the reply if the
  number check caught anything, even a number the retry fixed. It passed every
  check ($0.05).
- **`draft`** asks which champion to pick and how the champions do against Lee
  Sin. Two grader checks fail a reply that names a pick, leans towards one or
  ranks them, or that claims anything about a matchup. It passed every check
  ($0.05), but with a rounded number that every check missed (see the limits
  below).
- **`mid_peers`** (v8) asks "What should I work on in my mid games?" as a Gold
  mid laner picked at random from the ladder, shown to the coach as "you" with
  a placeholder name. A code check passes only if every benchmark comparison
  uses their own peer cohort, Gold mid laners. Run once on Sonnet 5.5, it passed
  every check ($0.07): it compared with `gold_middle` alone and led with the one
  finding, control wards. One soft spot: it listed early deaths, which aren't a
  finding, as something to keep an eye on, though it called them only a possible
  pattern.


## Results on a local model, 8 cases

The same 8 questions on `qwen3:4b` (`uv run python -m eval.run live --model local
--confirm`, $0 for the coach, $0.02 for the grader), against the last Opus run:

| | Opus 5.5 | qwen3:4b |
|---|---|---|
| Answered | 8 / 8 | 5 / 8 |
| Checks passed | 48 / 51 | 28 / 33 |
| Checks failed on the 5 cases both answered | 1 | 5 |
| The number check passed | 8 / 8 | 5 / 5 |
| Time per answer | 8 to 35 s | 4½ to 16 min |

Three questions never got an answer: two reached the 600-second limit on one
Ollama call, and one the 30-minute limit per case. They're in `errors.jsonl`, not
counted as failures.

Every local answer passed the number check, including three that were wrong:
- It said the player destroys fewer wards than Silver; the data says more.
- It gave Silver's game count, 19, as the player's.
- It called gold at minute 10 "gold per minute".

All three numbers exist in the tool results, so the code check can't object. The
Haiku grader caught all three. The fourth failure was two champions called
weaknesses from 3 and 4 games. The code check and the model grader catch
different failures, so both are needed (see DECISIONS.md).

**Limits:**
- **The number check proves a number exists, not that it belongs to that
  stat.** Citations (v9) close most of this on Claude models: a cited number
  must equal its own field. What they can't catch is a number from the right
  field in a wrong sentence, such as `mundo`'s "8 or fewer games each" cited to
  the losses' 8 when the wins had 9. The v9 re-run of `wins` gave another: the
  dragon samples as "177 vs 54", with 54 cited correctly to the Baron losses
  sample. The local model still has the whole gap.
  The local model's three wrong answers above are one case of this.
  Another came from Opus on the `draft` case. It wrote that the win rates have
  "margins of around ±25 points", rounding the 24.5 and 24.7 in its own table.
  That breaks the rule against rounding, but it passed, because 25 is in the
  tool result as Viego's 25.0% win rate. The grader's wrong-stat check passed
  it too. Neither check can tell a rounded number from an unrelated one that
  happens to match. The v8 run found another, on `mundo`: the win and loss
  splits had "8 or fewer" games each, when the wins had 9. It passed the number
  check because 8 is in the same result as the losses' count. The grader's
  wrong-stat check caught this one.
- **A calculation done in words passes the number check.** The check reads
  numbers, so a comparison that needs arithmetic but states no number gets
  through. On `stretch_no_tool` in the v8 run, the coach rightly refused to give
  the gold lost from 10 to 15 minutes, then wrote that "the gap grows faster in
  games you lose": a comparison of two changes no tool computed. Only the
  grader's check for computed values caught it.
- **The sample is small.** With 8 cases run once, a difference in pass rate under
  about 35 points is noise, so one run can't tell two models apart. Comparing
  models needs more cases and repeated runs (`--reps`).
- **Haiku grades a model from its own family.** Graders can favour answers that
  resemble their own family's. The checks are narrow rules rather than taste,
  which limits this, but doesn't remove it. A grader from another family, or a
  person reading the graded failures, would be the cross-check.

## The full run on a local model

All 16 cases on `qwen3:4b` through Ollama, on 2026-11-08, graded by Haiku 5.5 as
usual. The coach cost $0, the grader $0.06. The run took 4 hours 12 minutes: 12
answers averaged about 13 minutes each, and 4 cases (`viego`, `stretch_no_tool`,
`draft_options`, `top_lane`) hit the 600-second limit on one Ollama call. Those 4
are in `errors.jsonl`, not counted as failures. The local model isn't asked to
cite, so it keeps the plain number check.

| | Opus 5.5, 2026-11-07 | qwen3:4b |
|---|---|---|
| Answered | 16 / 16 | 12 / 16 |
| Checks passed | 102 / 113 | 74 / 84 |
| The number check passed | 15 / 16 | 12 / 12 |

**Where it failed:**
- **`draft`:** it chose Dr. Mundo as "the best option" on 17 games with a 24.5-point
  margin and no verdict, and said it counters Lee Sin, a matchup claim no tool
  makes. Four of five grader checks failed.
- **`emerald_lane`:** it compared gold with Emerald junglers, which this cohort
  marks as not comparable.
- **`work_on`:** it listed "avoid early deaths" as a thing to work on, though
  deaths had no verdict (`nothing_clear`). The prompt says never to. The grader
  missed this one. It also put the whole-game 1.4 CS a minute under "the first 10
  minutes", which the grader caught.
- **`weakest`:** a wrong sample-size note.
- **`wins`:** it wrote out its own reasoning and stopped without calling a tool.
  With no numbers, it passed the number check, and the grader passed it too; only
  the check that a tool was called failed. The app now shows "The local model
  didn't answer" for a reply like this.
- **`says`, twice:** on `bot_no_benchmark` the reply was right ("your gold_bottom
  benchmark has no data"), but in words the check's pattern doesn't match. On
  `support_vision` the case asked about a different player than on Opus: a Silver
  support synced later was listed first. The eval now picks each case's player by
  a fixed rule, so that row isn't a like-for-like comparison.

**What held:** every code check that ran. The role arguments were right 3 of 3
times, and the cohort, compared-with and avoided-stat checks all passed. The
prompt rules didn't all hold: choosing a pick, comparing what isn't comparable and
working on a gap with no verdict each failed once on this model.

**Re-run of `wins` and `draft`**, on 2026-11-08, after the app stopped showing a
local reply that called no tool. The grader cost $0.003.
- **`wins`:** an Ollama call reached its 600-second limit, so there's no answer
  to grade, and the new "didn't answer" path wasn't reached.
- **`draft`:** answered in 876 seconds, against 981 in the full run, and passed
  every check this time: it named the gap without picking a champion, and said
  there's no matchup data. One run can't tell a fix from chance here: the prompt
  didn't change for this case.
