# League-Of-Legends-Coach

Personal League of Legends coach. See [CLAUDE.md](CLAUDE.md) for the project rules.

Phase 1 is data ingestion: Riot ID → PUUID → match IDs → match details and timelines.

## Setup

Requires Python 3.12, [uv](https://docs.astral.sh/uv/) and Docker.

1. Copy `.env.example` to `.env`, then set `RIOT_API_KEY` and `POSTGRES_PASSWORD`.
   Get a key from the [Riot Developer Portal](https://developer.riotgames.com).
   Development keys expire every 24 hours.
2. Start everything: `docker compose up --build -d`. This also applies migrations.

## Sync a player

```sh
curl -X POST localhost:8000/sync -H "Content-Type: application/json" \
  -d '{"game_name": "yuval34", "tag_line": "34343"}'
curl localhost:8000/sync/status
```

100 matches take about 4 minutes, because each match needs 2 calls and the limit
is 100 calls per 2 minutes. A sync can be run again safely: it fetches only what's
missing.

## Benchmarks

Compare your jungle stats with real Silver and Emerald games:

```sh
curl -X POST localhost:8000/benchmarks/pull -H "Content-Type: application/json" \
  -d '{"cohort": "silver", "max_matches": 500}'
curl localhost:8000/benchmarks/status
curl "localhost:8000/benchmarks/compare?cohort=silver"
curl "localhost:8000/benchmarks/compare?cohort=emerald&champion=Viego"
```

`max_matches` is the cohort's running total, so raise it to carry on. A pull saves
its progress as it goes and can be started again after a key expires. It can't
run alongside a sync, because they share one call budget. Benchmark data stays in
the `benchmark` schema. [DECISIONS.md](DECISIONS.md) explains the rules.

After updating `RIOT_API_KEY`, run `docker compose up -d api`. `restart` keeps
the old key.

## Coach

The coach is an LLM agent with one tool per stat. Every number it states must
appear in a tool result, and code checks that after each reply: a reply with an
unsupported number gets one retry, then is shown with a warning. To see the check
catch a made-up number, with a scripted model and no paid calls:

```sh
docker compose up -d db
uv run python scripts/demo_number_check.py
```

To ask a question, which makes paid model calls (the first two cost $0.08 and
$0.14 on Opus 5.5):

```sh
curl -X POST localhost:8000/coach -H "Content-Type: application/json" \
  -d '{"question": "How is my farming compared with Silver?"}'
```

The response has the answer, its `status` (`verified` when every number passed
the check), the tools called and the token usage. `COACH_MODEL` in `.env` picks
the model. `DECISIONS.md` explains what counts as a
finding and what the number check can't catch.

## Eval

The eval asks the real coach 8 questions and grades each answer. Checks that code
can do exactly are code: the number check passed, a tool was called, and the reply
says "no benchmark" for Dr. Mundo and "not enough data" for Viego. The rest are
graded by a model, Haiku 5.5, one call per property: a real number attached to the
wrong stat, gaps in different units ranked against each other, win-only or
loss-only rows presented as findings, claims the tools don't support, and numbers
written in words. For that last one, code first finds words like "twice" or
"thirty", and only replies with one go to the grader.

```sh
uv run python -m eval.run estimate                       # free
uv run python -m eval.run calibrate --reps 2 --confirm   # paid: grades the grader
uv run python -m eval.run live --confirm                 # paid: asks the coach
```

Paid modes print their cost estimate and refuse to run without `--confirm`.
Results, with every tool call and the grader's evidence, go to `eval/results/`.
Attempts that never produced an answer, such as timeouts, go to `errors.jsonl`,
so they never count as the coach failing.

The grader is checked before it's trusted: `calibrate` grades replies with known
verdicts, made by planting one error into a real coach reply, plus honest replies
it once got wrong. The latest run agrees on 65 of 66. Its one miss is a grader
that judged the same reply both ways across two passes, so calibration also
reports verdicts that change between passes.

### Results on Opus 5.5

The first run found real coach failures, such as ranking CS against wards as "the
biggest gap", and also grader mistakes. After fixing both, the same 8 questions:

| Check | How | First run | After fixes |
|---|---|---|---|
| The number check passed | Code | 7 / 8 | 8 / 8 |
| A tool was called | Code | 8 / 8 | 8 / 8 |
| Says "no benchmark" or "not enough data" | Code | 1 / 2 | 2 / 2 |
| Numbers in words | Code, then model | 6 / 8 | 8 / 8 |
| Ranking gaps in different units | Model | 1 / 4 | 4 / 4 |
| Win-only or loss-only rows as findings | Model | 1 / 3 | 3 / 3 |
| A real number on the wrong stat | Model | 7 / 8 | 7 / 8 |
| Claims the tools don't support | Model | 6 / 8 | 6 / 8 |
| Presents both Silver findings | Model | 1 / 1 | 1 / 1 |
| No relative stats compared against Emerald | Model | 1 / 1 | 1 / 1 |
| **Total** | | **39 / 51** | **48 / 51** |

Each run cost about $0.85. The grader's rubrics changed between the runs too, so
not all of the gain is the coach's. Two of the three remaining failures led to
small fixes, a prompt line and a grader input, that haven't been through a live
run yet.

**Limits:**
- **The sample is small.** With 8 cases run once, a difference in pass rate under
  about 35 points is noise, so one run can't tell two models apart. Comparing
  models needs more cases and repeated runs (`--reps`).
- **Haiku grades a model from its own family.** Graders can favour answers that
  resemble their own family's. The checks are narrow rules rather than taste,
  which limits this, but doesn't remove it. A grader from another family, or a
  person reading the graded failures, would be the cross-check.

## Backups

```sh
docker compose up -d db
uv run python scripts/backup.py
```

This writes the whole database to a dated, compressed file in `backups/`, which
git ignores. To restore one into an empty database:

```sh
docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d <database>' < backups/<file>.dump
```

## Rate limiting

The limiter uses a sliding window even though Riot counts in fixed windows,
because we can't see when Riot's windows reset, and keeping every span under the
limit is safe wherever they start, at the cost of slightly lower throughput.

Its state lives in memory, so the app must run as a single process.

## Tests

```sh
docker compose up -d db
uv run pytest
```

Tests use a separate `lolcoach_test` database.
