# LoL Coach

A personal League of Legends jungle coach. It pulls my matches from the Riot API,
computes every stat in SQL, compares them with real Silver and Emerald junglers,
and uses an LLM agent to explain them in plain language. The model never
produces a number: it calls one tool per stat, and code checks that every number
in its answer appears in a tool result.

![The Overview page on my real games, Riot ID hidden: behind Silver junglers on farm, ahead on vision](docs/screens/overview.png)

- [The web app](#the-web-app): the four pages.
- [DECISIONS.md](DECISIONS.md): why each stat works the way it does, with the data
  behind each choice.
- [Eval](#eval): how the coach is tested, with results and limits.
- [CLAUDE.md](CLAUDE.md): the project's rules.

**This is a personal tool, not a public service.** It runs on Riot's development
key, which is for personal use: a public app needs a production key approved by
Riot. Every coach question is also a paid model call, and the benchmark is built
from other players' matches, which belong in a local database rather than on a
server. LoL Coach isn't endorsed by Riot Games.

## The web app

A React app in [web/](web/) reads the API and draws; it never computes a stat.
Every verdict, gap, margin and percentage comes from the API. The screenshots are
my real games, with the Riot ID swapped for a placeholder.

```sh
cd web
npm install
npm run dev     # http://localhost:5173, with the API on port 8000
```

**Overview:** a headline written by code from the findings, then each theme's
telling measures as bars from zero, with a plain verdict and the gap in words.
Margins wait behind a hover. Context the verdict doesn't use, such as trinket
wards and vision score, sits under the theme marked "not judged" (above).

**Champions:** a role filter, a table sorted by any column, and each win rate's
range on hover. Champions on fewer than 10 games are hatched and greyed wherever
the sort puts them, and only champions with enough games offer "Ask the coach".

![The Champions page: a sortable table, with champions under 10 games hatched](docs/screens/champions.png)

**Compare:** Silver and Emerald at once. Gold and CS at 10, 15 and 20 minutes,
with your likely range shaded, then every theme's verdict against both ranks.

![The Compare page: gold and CS by minute against Silver and Emerald](docs/screens/compare.png)

**Coach:** each reply comes with a receipt worked out by the server, not the
model: the number check, every tool called with the games it rested on, and the
cost. Questions are only sent on the Ask button.

![The Coach page: a reply on deaths, with its number check, tools and cost](docs/screens/coach.png)

The older Gradio UI in `ui/` still works and is what the demo below uses.

## Try it in demo mode

The demo has 12 of my jungle games with every player's identity replaced, so you
can try it without a Riot key. Requires Python 3.12, [uv](https://docs.astral.sh/uv/)
and Docker.

1. Copy `.env.example` to `.env`. Set `POSTGRES_PASSWORD`, and set
   `POSTGRES_DB=lolcoach_demo`.
2. Start the database and load the demo:
   ```sh
   docker compose up -d db
   uv run python -m demo.load
   ```
3. Start the API and the UI, then open http://127.0.0.1:7860:
   ```sh
   docker compose up --build -d api
   uv run python -m ui.app
   ```

The **Stats** tab works as it is. **Asking the coach needs an Anthropic API key**
in `ANTHROPIC_API_KEY`, and each question is a paid call, usually a few cents to
about $0.30. With 12 games, most stats are under the 10-game floor, so expect
"not enough data" often: that's the coach being honest, not broken. The demo has
no benchmark, so comparisons say there isn't one.

**About the anonymization:** names, PUUIDs, summoner IDs, match IDs and real dates
are replaced, and the export refuses to write the file if any original value is
left. Stats and champions are kept, though. So someone who already knows my Riot
ID could find these games in a public match history and see who played in them.

## Setup with your own data

Requires Python 3.12, [uv](https://docs.astral.sh/uv/) and Docker.

1. Copy `.env.example` to `.env`, then set `RIOT_API_KEY` and `POSTGRES_PASSWORD`.
   Get a key from the [Riot Developer Portal](https://developer.riotgames.com).
   Development keys expire every 24 hours.
2. Start everything: `docker compose up --build -d`. This also applies migrations.

## Sync a player

```sh
curl -X POST localhost:8000/sync -H "Content-Type: application/json" \
  -d '{"game_name": "YourName", "tag_line": "TAG"}'
curl localhost:8000/sync/status
```

100 matches take about 4 minutes, because each match needs 2 calls and the limit
is 100 calls per 2 minutes. A sync can be run again safely: it fetches only what's
missing.

The first player synced is the owner: the default on every page and the one the
eval runs on. Other players can be added from the web app's Players page, and
their games stay in the same local database. Every stat, comparison and coach
answer is about one player, picked by the server; the model never sees or
chooses a PUUID. A player only gets a benchmark their rank and role fit: Silver
for Silver junglers, Emerald as a target for junglers below Emerald. Anyone else
sees "no benchmark", never another player's or another rank's comparison. Ranks
are current solo/duo ranks, because match data doesn't record rank per game.

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
the default model. `DECISIONS.md` explains what counts as a
finding and what the number check can't catch.

### Picking a model

The web app's Coach page has a model picker under the chat box: Opus 5.5,
Sonnet 5.5, Haiku 5.5 and a local model. Each shows an estimated cost per
question: the average token use of a real Opus answer in the last eval, priced
for that model (about $0.10, $0.05 and under $0.01). The choice is remembered in
the browser. `POST /coach` takes it as `"model"`, and `GET /coach/models` lists
the choices. Every model gets the same prompt, tools, benchmark rules and number
check.

### The local model

`"model": "local"` runs `qwen3:4b` in [Ollama](https://ollama.com) on this
computer: free, but several minutes per answer and less reliable. It was picked for a 4 GB GPU as the largest
model that fits there and supports tool calls.

```sh
ollama pull qwen3:4b
```

The context is set to 32,768 tokens, because a full comparison is about 12,000
and Ollama's default would silently cut tool results short. On a 4 GB GPU that
context doesn't fit in video memory, so most of the work runs on the CPU and an
answer takes several minutes. qwen3 also reasons in its answer even with
thinking off; only the text after its reasoning is kept, so the number check
never sees made-up numbers from it.

## API keys

The web app's Settings page replaces the Riot and Anthropic keys without a
restart. Each new key is tested with one cheap call first (Riot's server
status, through the rate limiter; listing Anthropic's models, which uses no
tokens) and saved to `.env` only if it works. `.env` stays the only place keys
live: Compose mounts it into the API container, which rewrites just the key's
line. No endpoint returns a key; the page sees only the last 4 characters, when
it was set and, for Riot, when it expires.

The settings endpoints only answer this computer's web app: the API port is
bound to `127.0.0.1`, the request must name `localhost` as its host, and it must
carry a header that only the app's own page sends. After changing `.env` by
hand, recreate the container (`docker compose up -d --force-recreate api`): a
restart keeps the old environment.

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
it once got wrong. The latest run agrees on 63 of 66. Its one miss is a grader
that judged the same reply both ways across two passes, so calibration also
reports verdicts that change between passes.

### Results on Opus 5.5

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

### Results on a local model

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
