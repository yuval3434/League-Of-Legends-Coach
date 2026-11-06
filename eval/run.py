"""Run the eval. Paid modes need --confirm; without it they print the estimate.

    uv run python -m eval.run estimate
    uv run python -m eval.run calibrate --confirm
    uv run python -m eval.run live --model claude-sonnet-5-5 --confirm

`calibrate` grades labelled replies, to measure the judge. `live` asks the real
coach every case and grades the answers. Results go to eval/results/<run>/:
results.jsonl has one row per graded answer, errors.jsonl has attempts that never
produced one, such as timeouts and API failures, so plumbing never scores as the
coach failing.
"""

import argparse
import asyncio
import json
import sys
import time
from collections import defaultdict
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import anthropic
from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agent.coach import CoachAnswer, ask_coach
from agent.llm import LOCAL_PREFIX, LocalModelError, ModelClient, Usage, create_model
from agent.options import OPTIONS_MAX_TOKENS, prepare
from agent.tools import ToolContext
from benchmarks.models import create_benchmark_engine
from benchmarks.cohorts import cohorts_for
from ingestion.players import SelectedPlayer, list_players, load_player
from eval.calibration import load_examples, load_tool_outputs
from eval.cases import CASES, Case
from eval.checks import number_words, run_code_check
from agent.pricing import PRICES, cost, price_of
from eval.judge import JUDGE_MODEL, format_tool_outputs, grade
from ingestion.config import Settings

RESULTS = Path(__file__).parent / "results"
CASE_TIMEOUT_S = 300
# A small local model on a 4 GB GPU re-reads every tool result each step, slowly.
LOCAL_CASE_TIMEOUT_S = 1800

# For the estimate: what the first two real questions cost on Opus 5.5.
MEASURED_OPUS_COST = {"narrow": 0.084, "broad": 0.142}
BROAD_CASES = {"work_on", "weakest", "mid_peers"}
CHARS_PER_TOKEN = (4.0, 2.5)
JUDGE_OUTPUT_TOKENS = (300, 2000)


def _error(case: str, rep: int, kind: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"case": case, "rep": rep, "error": kind, "message": message, **extra}


async def _judge_checks(
    client: AsyncAnthropic, judge_model: str, case: Case, answer: CoachAnswer, outputs: str
) -> tuple[dict[str, Any], Usage]:
    checks: dict[str, Any] = {}
    used = Usage()
    for criterion in case.judge_checks:
        words = number_words(answer.text) if criterion == "number_words" else None
        if words == []:
            checks[criterion] = {"by": "code", "passed": True, "detail": "no number words"}
            continue
        try:
            verdict = await grade(client, criterion, case.question, answer.text, outputs, judge_model)
        except anthropic.APIError as error:
            checks[criterion] = {"by": "judge", "status": "error", "passed": None, "detail": repr(error)}
            continue
        used += verdict.usage
        checks[criterion] = {
            "by": "judge",
            "status": verdict.status,
            "passed": verdict.passed,
            "detail": verdict.evidence,
            "judge_model": verdict.model,
            **({"words": words} if words else {}),
        }
    return checks, used


async def _ask(model: ModelClient, context: ToolContext, case: Case) -> CoachAnswer:
    """A plain question, or an options board the way the Draft page's button asks it."""
    if case.options_board is None:
        return await ask_coach(model, context, case.question, case.hidden_tools)
    prepared = await prepare(context, case.options_board, getattr(model, "cites", False))
    return await ask_coach(
        model,
        context,
        prepared.question,
        preloaded=prepared.preloaded,
        offer_tools=False,
        max_tokens=OPTIONS_MAX_TOKENS,
    )


async def run_case(
    model: ModelClient,
    model_id: str,
    context: ToolContext,
    client: AsyncAnthropic,
    judge_model: str,
    case: Case,
    rep: int,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return (row, None) for a graded answer, or (None, error) for a failed attempt."""
    player = context.player if context else None
    peer = cohorts_for(player.rank_tier, player.main_role)[0] if player and player.main_role else None
    return await _run_case(model, model_id, context, client, judge_model, case, rep, peer)


async def _run_case(
    model: ModelClient,
    model_id: str,
    context: ToolContext,
    client: AsyncAnthropic,
    judge_model: str,
    case: Case,
    rep: int,
    peer: str | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Run one case; `peer` is the player's own peer cohort, for right_cohort."""
    started = time.monotonic()
    limit = LOCAL_CASE_TIMEOUT_S if model_id == "local" else CASE_TIMEOUT_S
    try:
        answer = await asyncio.wait_for(_ask(model, context, case), limit)
    except TimeoutError:
        return None, _error(case.id, rep, "timeout", f"over {limit} s")
    except (anthropic.APIError, LocalModelError) as error:
        return None, _error(case.id, rep, "api_error", repr(error))

    row: dict[str, Any] = {
        "case": case.id,
        "rep": rep,
        "model": model_id,
        "served_models": sorted(set(answer.models)),
        "question": case.question,
        "status": answer.status,
        "text": answer.text,
        "tools_called": answer.tools_called,
        "caught_numbers": answer.caught_numbers,
        "tool_log": [asdict(log) for log in answer.tool_log],
        "citations": answer.citations,
        "usage": asdict(answer.usage),
        "coach_cost": cost(answer.usage, model_id),
        "seconds": round(time.monotonic() - started, 1),
        "checks": {},
    }
    # A local model answers as "ollama:<name>"; any other model must be the one asked for.
    if model_id == "local":
        mismatch = not all(m.startswith(LOCAL_PREFIX) for m in answer.models)
    else:
        mismatch = bool(set(answer.models) - {model_id})
    if mismatch:
        return None, _error(case.id, rep, "served_model_mismatch", str(answer.models), row=row)
    if answer.status not in ("verified", "unverified"):
        # Refused, cut off or abandoned: counted as its own outcome, not graded.
        return row, None

    for name in case.code_checks:
        check = run_code_check(name, answer, case.says, peer)
        row["checks"][name] = {"by": "code", "passed": check.passed, "detail": check.detail}
    outputs = format_tool_outputs(row["tool_log"])
    if answer.citations:
        # Where each number in the reply was copied from, for the wrong-stat check.
        cited = "\n".join(f"{c['number']}: {c['label']}" for c in answer.citations)
        outputs += (
            "\n\nCitations: each number in the reply and the field it was copied from.\n" + cited
        )
    judged, judge_usage = await _judge_checks(client, judge_model, case, answer, outputs)
    row["checks"] |= judged
    row["judge_model"] = judge_model
    row["judge_usage"] = asdict(judge_usage)
    row["judge_cost"] = cost(judge_usage, judge_model)
    return row, None


def summarize_live(rows: list[dict[str, Any]], errors: list[dict[str, Any]]) -> dict[str, Any]:
    by_check: dict[str, list[bool]] = defaultdict(list)
    method: dict[str, set[str]] = defaultdict(set)
    judge_errors = 0
    for row in rows:
        for name, check in row["checks"].items():
            method[name].add(check["by"])
            if check["passed"] is None:
                judge_errors += 1
            else:
                by_check[name].append(check["passed"])
    return {
        "answers": len(rows),
        "failed_attempts": len(errors),
        "statuses": dict(sorted(_count(row["status"] for row in rows).items())),
        "checks": {
            name: {
                "passed": sum(results),
                "graded": len(results),
                "by": "+".join(sorted(method[name])),
            }
            for name, results in sorted(by_check.items())
        },
        "judge_errors": judge_errors,
        "failures": [
            {"case": row["case"], "rep": row["rep"], "check": name, "detail": check["detail"]}
            for row in rows
            for name, check in row["checks"].items()
            if check["passed"] is False
        ],
        "coach_cost": round(sum(row["coach_cost"] for row in rows), 4),
        "judge_cost": round(sum(row.get("judge_cost", 0) for row in rows), 4),
    }


def summarize_calibration(rows: list[dict[str, Any]]) -> dict[str, Any]:
    graded = [row for row in rows if row["status"] == "ok"]
    by_criterion: dict[str, list[bool]] = defaultdict(list)
    verdicts: dict[str, set[bool]] = defaultdict(set)
    for row in graded:
        by_criterion[row["criterion"]].append(row["passed"] == row["expected_pass"])
        verdicts[row["id"]].add(row["passed"])
    return {
        "agreement": {"matched": sum(sum(v) for v in by_criterion.values()), "graded": len(graded)},
        "by_criterion": {
            name: {"matched": sum(v), "graded": len(v)} for name, v in sorted(by_criterion.items())
        },
        "inconsistent_examples": sorted(i for i, v in verdicts.items() if len(v) > 1),
        "judge_errors": len(rows) - len(graded),
        "disagreements": [
            {"id": row["id"], "rep": row["rep"], "expected_pass": row["expected_pass"], "evidence": row["evidence"]}
            for row in graded
            if row["passed"] != row["expected_pass"]
        ],
        "judge_cost": round(sum(row["judge_cost"] for row in rows), 4),
    }


def _count(items: Any) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for item in items:
        counts[item] += 1
    return counts


async def calibrate(client: AsyncAnthropic, judge_model: str, reps: int, out: Path) -> dict[str, Any]:
    examples = load_examples()
    outputs = {e.context: format_tool_outputs(load_tool_outputs(e.context)) for e in examples}
    rows = []
    for rep in range(reps):
        for example in examples:
            verdict = await grade(
                client,
                example.criterion,
                example.question,
                example.reply,
                outputs[example.context],
                judge_model,
            )
            rows.append(
                {
                    "id": example.id,
                    "criterion": example.criterion,
                    "rep": rep,
                    "expected_pass": example.expected_pass,
                    "status": verdict.status,
                    "passed": verdict.passed,
                    "evidence": verdict.evidence,
                    "judge_model": verdict.model,
                    "judge_cost": cost(verdict.usage, judge_model),
                }
            )
    _write_jsonl(out / "calibration.jsonl", rows)
    return summarize_calibration(rows)


async def live(
    model: ModelClient,
    model_id: str,
    contexts: dict[str, ToolContext],
    client: AsyncAnthropic,
    judge_model: str,
    cases: list[Case],
    reps: int,
    out: Path,
) -> dict[str, Any]:
    rows, errors = [], []
    for rep in range(reps):
        for case in cases:
            context = contexts[case.player]
            row, error = await run_case(model, model_id, context, client, judge_model, case, rep)
            print(f"  {case.id} rep {rep}: {row['status'] if row else error['error']}", flush=True)
            rows += [row] if row else []
            errors += [error] if error else []
    _write_jsonl(out / "results.jsonl", rows)
    _write_jsonl(out / "errors.jsonl", errors)
    return summarize_live(rows, errors)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, default=str) + "\n" for row in rows), encoding="utf-8")


def estimate(models: list[str], cases: list[Case], reps: int, calibration_reps: int) -> list[str]:
    """Rough cost before a paid run. Every input is a measured size or cost."""
    context_chars = len(format_tool_outputs(load_tool_outputs()))
    judge_calls = sum(len(case.judge_checks) for case in cases) * reps
    examples = len(load_examples()) * calibration_reps
    haiku = PRICES[JUDGE_MODEL]
    lines = []

    def judge_cost(calls: int, bound: int) -> float:
        tokens = context_chars / CHARS_PER_TOKEN[bound]
        # Low: the shared tool results are cached after the first call. High: never.
        read = tokens * (calls - 1) * haiku["read"] if bound == 0 else tokens * calls * haiku["input"]
        write = tokens * haiku["write"] if bound == 0 else 0
        return (read + write + calls * JUDGE_OUTPUT_TOKENS[bound] * haiku["output"]) / 1e6

    for model in models:
        ratio = price_of(model)["output"] / PRICES["claude-opus-5-5"]["output"]
        base = sum(
            MEASURED_OPUS_COST["broad" if case.id in BROAD_CASES else "narrow"] for case in cases
        ) * reps * ratio
        lines.append(
            f"live, {model}: coach ${base * 0.5:.2f} to ${base * 2:.2f} "
            f"for {len(cases)} cases x {reps} rep(s), judge ${judge_cost(judge_calls, 0):.3f} "
            f"to ${judge_cost(judge_calls, 1):.3f} for up to {judge_calls} judge calls"
        )
    lines.append(
        f"calibrate: judge ${judge_cost(examples, 0):.3f} to ${judge_cost(examples, 1):.3f} "
        f"for {examples} judge calls"
    )
    return lines


async def non_jungler(sessions: Any, players: list[dict[str, Any]]) -> SelectedPlayer | None:
    """The first synced player who mains a role other than jungle, shown to the
    coach as the owner, so it says "you" and the saved results never name them."""
    row = next(
        (p for p in players if not p["is_owner"] and p["main_role"] not in (None, "JUNGLE")),
        None,
    )
    if row is None:
        return None
    async with sessions() as session:
        player = await load_player(session, row["puuid"])
    return replace(player, is_owner=True, game_name="Player", tag_line="EVAL")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=["estimate", "calibrate", "live"])
    parser.add_argument("--model", action="append", help="coach model; repeat to estimate several")
    parser.add_argument("--judge-model", default=JUDGE_MODEL)
    parser.add_argument("--reps", type=int, default=1)
    parser.add_argument("--cases", help="comma-separated case ids")
    parser.add_argument("--confirm", action="store_true", help="allow paid calls")
    args = parser.parse_args()

    settings = Settings()
    models = args.model or [settings.coach_model]
    cases = [c for c in CASES if not args.cases or c.id in args.cases.split(",")]
    print("\n".join(estimate(models, cases, args.reps, args.reps)))
    if args.mode == "estimate":
        return 0
    if not args.confirm:
        print("\nThis makes paid calls. Add --confirm to run it.")
        return 1
    key = settings.anthropic_api_key.get_secret_value()
    if not key:
        print("ANTHROPIC_API_KEY isn't set in .env")
        return 1

    client = AsyncAnthropic(api_key=key)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if args.mode == "calibrate":
        out = RESULTS / f"{stamp}-calibrate-{args.judge_model}"
        out.mkdir(parents=True)
        summary = await calibrate(client, args.judge_model, args.reps, out)
    else:
        [model_id] = models
        if model_id == args.judge_model:
            print("The judge must be a different model from the coach.")
            return 1
        sessions = async_sessionmaker(create_async_engine(settings.database_url))
        benchmark = async_sessionmaker(create_benchmark_engine(settings))
        # The owner, and for some cases a player in another role, asked as "you".
        async with sessions() as session:
            owner = await load_player(session)
            others = await list_players(session)
        if owner is None:
            print("No owner synced yet: run POST /sync first.")
            return 1
        contexts = {"owner": ToolContext(sessions, benchmark, (owner.puuid,), owner)}
        if any(case.player == "non_jungler" for case in cases):
            other = await non_jungler(sessions, others)
            if other is None:
                print("No synced player mains a role other than jungle: sync one first.")
                return 1
            contexts["non_jungler"] = ToolContext(sessions, benchmark, (other.puuid,), other)
        model = create_model(settings, model_id)
        # Windows paths can't hold the ":" in a local model's name, such as qwen3:4b.
        name = f"local-{settings.local_model}" if model_id == "local" else model_id
        out = RESULTS / f"{stamp}-live-{name.replace(':', '-')}"
        out.mkdir(parents=True)
        summary = await live(model, model_id, contexts, client, args.judge_model, cases, args.reps, out)
    (out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    print(f"\nSaved to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
