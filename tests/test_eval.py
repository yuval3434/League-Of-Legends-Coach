"""The eval's plumbing, with fake models: no paid calls."""

import asyncio
import json

import httpx2
import pytest
from anthropic import AsyncAnthropic, DefaultAsyncHttpxClient
from fakes import FakeModel, calls, says

import eval.run as run
from agent.coach import CoachAnswer
from agent.llm import Usage
from eval.calibration import load_examples
from eval.cases import CASES, Case
from eval.checks import first_try, number_words, says as says_check, verified
from eval.judge import CRITERIA, Verdict, grade

CASE = Case("t", "How's my farming?", ("unit_comparison",), says=("not enough data",))


def answer(text="Fine.", status="verified"):
    return CoachAnswer(text, status)


def judge_client(reply_text, stop_reason="end_turn"):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx2.Response(
            200,
            json={
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "claude-haiku-5-5",
                "content": [{"type": "text", "text": reply_text}],
                "stop_reason": stop_reason,
                "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        )

    client = AsyncAnthropic(
        api_key="test",
        max_retries=0,
        http_client=DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    return client, requests


# Code checks


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("You place twice as many wards.", ["twice"]),
        ("Across thirty games, about half.", ["half", "thirty"]),
        ("You average 5.45.", []),
        ("Someone and nothing else.", []),
    ],
)
def test_number_words_are_found_as_whole_words(text, found):
    assert number_words(text) == found


def test_a_verified_answer_passes_and_others_fail():
    assert verified(answer()).passed
    assert not verified(answer(status="unverified")).passed


def test_a_phrase_matches_whatever_the_case_and_quotes():
    assert says_check(answer("There’s Not Enough Data here."), ("not enough data",)).passed
    assert not says_check(answer("Nothing to say."), ("not enough data",)).passed


@pytest.mark.parametrize(
    "text",
    [
        "No Silver benchmark exists for him yet.",
        "There's no benchmark for Dr. Mundo.",
        "Dr. Mundo isn't a benchmark champion... there is not yet a benchmark.",
        "Mundo doesn't have a benchmark.",
    ],
)
def test_the_mundo_check_accepts_honest_wordings(text):
    mundo = next(case for case in CASES if case.id == "mundo")
    assert says_check(answer(text), mundo.says).passed


def test_the_mundo_check_rejects_a_benchmark_number():
    mundo = next(case for case in CASES if case.id == "mundo")
    assert not says_check(answer("Silver Mundo players average 6.1 CS."), mundo.says).passed


STRETCH = next(case for case in CASES if case.id == "stretch_no_tool")


@pytest.mark.parametrize(
    "text",
    [
        "I don't have gold lost between minutes 10 and 15.",
        "That stretch isn't in my data: I only see the gap at 10 and at 15.",
        "I can't give you an amount for that stretch.",
        "The tools don’t have per-stretch numbers.",
    ],
)
def test_the_stretch_check_accepts_honest_wordings(text):
    assert says_check(answer(text), STRETCH.says).passed


def test_the_stretch_check_rejects_a_worked_out_amount():
    text = "You're 219 behind at 10 and 461 at 15, so you lose about 242 between them."
    assert not says_check(answer(text), STRETCH.says).passed


def test_a_number_fixed_by_the_retry_still_fails_first_try():
    fixed = CoachAnswer("I don't have that.", "verified", caught_numbers=["242"])
    assert verified(fixed).passed
    assert not first_try(fixed).passed
    assert first_try(answer()).passed


def test_the_stretch_case_runs_without_the_stretch_tool():
    assert STRETCH.hidden_tools == ("farm_by_stretch",)
    assert "first_try" in STRETCH.code_checks
    assert {"no_computed", "no_overclaim"} <= set(STRETCH.judge_checks)


DRAFT = next(case for case in CASES if case.id == "draft")


@pytest.mark.parametrize(
    "text",
    [
        "There's no matchup data, so I can't say how they do against Lee Sin.",
        "I don't have matchup data for any of them.",
        "I have no data on how your champions do against Lee Sin.",
    ],
)
def test_the_draft_check_accepts_saying_there_is_no_matchup_data(text):
    assert says_check(answer(text), DRAFT.says).passed


def test_the_draft_check_rejects_a_matchup_guess():
    text = "Dr. Mundo is a safe pick into Lee Sin, he outscales him."
    assert not says_check(answer(text), DRAFT.says).passed


def test_the_draft_case_checks_the_pick_and_the_matchups():
    assert {"no_pick_chosen", "no_matchup_claim", "no_overclaim"} <= set(DRAFT.judge_checks)
    assert DRAFT.hidden_tools == ()


OPTIONS = next(case for case in CASES if case.id == "draft_options")


def test_the_options_case_needs_the_general_knowledge_label():
    labelled = "All of this is general game knowledge from Riot's text, not from your games."
    assert says_check(answer(labelled), OPTIONS.says).passed
    assert says_check(answer("Per Riot's tips, stay spread out."), OPTIONS.says).passed
    assert not says_check(answer("Dr. Mundo heals through long fights."), OPTIONS.says).passed
    assert {"no_pick_chosen", "no_matchup_claim"} <= set(OPTIONS.judge_checks)


async def test_an_options_case_is_asked_the_way_the_button_asks(monkeypatch):
    from agent.coach import ToolLog
    from agent.options import OPTIONS_MAX_TOKENS, Prepared

    boards = []

    async def fake_prepare(context, board, cite=False):
        boards.append(board)
        log = ToolLog("draft_board", board, '{"pool": []}', False)
        return Prepared("Options for this draft. [results]", (log,), ["DrMundo"])

    monkeypatch.setattr(run, "prepare", fake_prepare)
    model = FakeModel(says("General game knowledge from Riot's text. The pick is yours."))

    reply = await run._ask(model, None, OPTIONS)

    assert boards == [OPTIONS.options_board]
    assert (model.tools, model.max_tokens) == ([], [OPTIONS_MAX_TOKENS])
    assert model.sent[0][0]["content"] == "Options for this draft. [results]"
    assert reply.tools_called == ["draft_board"] and reply.status == "verified"


def test_the_judge_sees_each_tools_description():
    from eval.judge import format_tool_outputs

    text = format_tool_outputs([{"name": "win_rate_by_gold_diff", "arguments": {}, "content": "{}"}])
    assert "at minute 10" in text


def test_every_case_uses_known_checks():
    for case in CASES:
        assert set(case.judge_checks) <= set(CRITERIA), case.id


def test_the_cases_cover_what_was_asked_for():
    judged = {check for case in CASES for check in case.judge_checks}
    assert {"wrong_stat", "number_words", "unit_comparison", "split_as_finding"} <= judged
    for case_id, text in (("mundo", "no benchmark"), ("viego", "not enough data")):
        case = next(c for c in CASES if c.id == case_id)
        assert says_check(answer(text), case.says).passed


# Calibration set


def test_every_calibration_anchor_is_in_the_real_replies():
    # load_examples asserts each planted change finds its text exactly once.
    examples = load_examples()
    assert len({e.id for e in examples}) == len(examples)


def test_calibration_has_passes_and_fails_for_each_criterion():
    by_criterion = {}
    for example in load_examples():
        by_criterion.setdefault(example.criterion, set()).add(example.expected_pass)
    assert set(by_criterion) == set(CRITERIA)
    assert all(labels == {True, False} for labels in by_criterion.values())


# The judge


async def test_a_judge_verdict_is_read_from_structured_output():
    client, requests = judge_client(json.dumps({"evidence": "quote", "verdict": "fail"}))
    verdict = await grade(client, "wrong_stat", "Q", "Reply", "results")
    assert (verdict.status, verdict.passed, verdict.evidence) == ("ok", False, "quote")
    body = json.loads(requests[0].content)
    assert body["model"] == "claude-haiku-5-5"
    assert body["output_config"]["format"]["type"] == "json_schema"
    # Descriptions and results come before the reply, so calls share a cache.
    descriptions, results, rest = body["messages"][0]["content"]
    assert descriptions["text"].startswith("<tool_descriptions>")
    assert results["text"].startswith("<tool_results>")
    assert "<reply>\nReply\n</reply>" in rest["text"]


def test_the_judge_sees_tools_that_werent_called():
    from eval.judge import ALL_DESCRIPTIONS

    # The deaths tool defines the phase boundaries.
    assert "deaths_by_phase" in ALL_DESCRIPTIONS
    assert "15:00 to 25:00" in ALL_DESCRIPTIONS


@pytest.mark.parametrize(
    ("text", "stop_reason"),
    [("not json", "end_turn"), ('{"verdict": "maybe"}', "end_turn"), ("", "refusal")],
)
async def test_an_unusable_verdict_is_an_error_not_a_fail(text, stop_reason):
    client, _ = judge_client(text, stop_reason)
    verdict = await grade(client, "wrong_stat", "Q", "Reply", "results")
    assert verdict.status == "error"
    assert verdict.passed is None


# The runner


@pytest.fixture(autouse=True)
def prices_for_fakes(monkeypatch):
    """Cost lookups refuse unknown models, so the fakes get a price."""
    from agent.pricing import PRICES

    price = {"input": 1.0, "output": 1.0, "read": 1.0, "write": 1.0}
    monkeypatch.setitem(PRICES, "fake-model", price)
    monkeypatch.setitem(PRICES, "judge", price)


@pytest.fixture
def fake_judge(monkeypatch):
    graded = []

    async def grade(client, criterion, question, reply, outputs, model):
        graded.append(criterion)
        return Verdict("ok", criterion != "unit_comparison", "evidence", Usage(10, 5), model)

    monkeypatch.setattr(run, "grade", grade)
    return graded


async def run_one(model, case=CASE, model_id="fake-model"):
    return await run.run_case(model, model_id, None, None, "judge", case, 0)


async def test_a_case_gets_its_code_and_judge_checks(fake_judge):
    row, error = await run_one(FakeModel(says("There's not enough data.")))
    assert error is None
    assert {name: c["by"] for name, c in row["checks"].items()} == {
        "verified": "code",
        "used_tools": "code",
        "says": "code",
        "wrong_stat": "judge",
        "number_words": "code",
        "unit_comparison": "judge",
    }
    assert row["checks"]["says"]["passed"] is True
    assert row["checks"]["unit_comparison"]["passed"] is False
    assert fake_judge == ["wrong_stat", "unit_comparison"]


async def test_a_hidden_tool_is_neither_offered_nor_run(fake_judge):
    case = Case("h", "Gold lost from 10 to 15?", hidden_tools=("farm_by_stretch",), first_try=True)
    model = FakeModel(calls(("farm_by_stretch", {})), says("I don't have that."))

    row, error = await run_one(model, case)

    assert error is None
    assert "farm_by_stretch" not in [tool["name"] for tool in model.tools]
    # Asked for anyway, it answers as if the tool didn't exist.
    log = row["tool_log"][0]
    assert log["is_error"] and log["content"] == "There is no tool called farm_by_stretch."
    assert row["checks"]["first_try"]["passed"] is True


async def test_number_words_go_to_the_judge_only_when_present(fake_judge):
    row, _ = await run_one(FakeModel(says("You have twice the deaths.")))
    assert row["checks"]["number_words"]["by"] == "judge"
    assert row["checks"]["number_words"]["words"] == ["twice"]


async def test_a_refusal_is_recorded_but_not_graded(fake_judge):
    row, error = await run_one(FakeModel(says("No.", stop_reason="refusal")))
    assert error is None
    assert row["status"] == "refused"
    assert row["checks"] == {}
    assert fake_judge == []


async def test_a_timeout_is_an_error_not_a_result(fake_judge, monkeypatch):
    class Slow:
        async def send(self, *args):
            await asyncio.sleep(1)

    monkeypatch.setattr(run, "CASE_TIMEOUT_S", 0.01)
    row, error = await run_one(Slow())
    assert row is None
    assert error["error"] == "timeout"


async def test_an_answer_from_another_model_is_an_error(fake_judge):
    row, error = await run_one(FakeModel(says("Fine.")), model_id="claude-opus-5-5")
    assert row is None
    assert error["error"] == "served_model_mismatch"


async def test_a_judge_error_is_left_out_of_the_pass_rate(fake_judge, monkeypatch):
    async def broken(client, criterion, question, reply, outputs, model):
        return Verdict("error", None, "unreadable", Usage(), model)

    monkeypatch.setattr(run, "grade", broken)
    row, _ = await run_one(FakeModel(says("There's not enough data.")))
    summary = run.summarize_live([row], [])
    assert summary["judge_errors"] == 2
    assert "wrong_stat" not in summary["checks"]


def test_the_live_summary_counts_passes_per_check():
    rows = [
        {"case": "a", "rep": 0, "status": "verified", "coach_cost": 0.1, "judge_cost": 0.01,
         "checks": {"x": {"by": "code", "passed": True, "detail": ""}}},
        {"case": "b", "rep": 0, "status": "verified", "coach_cost": 0.2, "judge_cost": 0.01,
         "checks": {"x": {"by": "code", "passed": False, "detail": "why"}}},
    ]
    summary = run.summarize_live(rows, [{"error": "timeout"}])
    assert summary["checks"]["x"] == {"passed": 1, "graded": 2, "by": "code"}
    assert summary["failed_attempts"] == 1
    assert summary["failures"] == [{"case": "b", "rep": 0, "check": "x", "detail": "why"}]
    assert summary["coach_cost"] == 0.3


def test_calibration_reports_agreement_and_inconsistency():
    rows = [
        {"id": "a", "criterion": "c", "rep": 0, "expected_pass": True, "status": "ok", "passed": True, "evidence": "", "judge_cost": 0},
        {"id": "a", "criterion": "c", "rep": 1, "expected_pass": True, "status": "ok", "passed": False, "evidence": "e", "judge_cost": 0},
        {"id": "b", "criterion": "c", "rep": 0, "expected_pass": False, "status": "error", "passed": None, "evidence": "", "judge_cost": 0},
    ]
    summary = run.summarize_calibration(rows)
    assert summary["agreement"] == {"matched": 1, "graded": 2}
    assert summary["inconsistent_examples"] == ["a"]
    assert summary["judge_errors"] == 1


def test_the_estimate_needs_no_api_key():
    lines = run.estimate(["claude-opus-5-5", "claude-sonnet-5-5"], list(CASES), 1, 2)
    assert len(lines) == 3
