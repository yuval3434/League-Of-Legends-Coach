"""The eval's plumbing, with fake models: no paid calls."""

import asyncio
import json

import httpx2
import pytest
from anthropic import AsyncAnthropic, DefaultAsyncHttpxClient
from fakes import FakeModel, says

import eval.run as run
from agent.coach import CoachAnswer
from agent.llm import Usage
from eval.calibration import load_examples
from eval.cases import CASES, Case
from eval.checks import number_words, says as says_check, verified
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


def test_every_case_uses_known_checks():
    for case in CASES:
        assert set(case.judge_checks) <= set(CRITERIA), case.id


def test_the_cases_cover_what_was_asked_for():
    judged = {check for case in CASES for check in case.judge_checks}
    assert {"wrong_stat", "number_words", "unit_comparison", "split_as_finding"} <= judged
    says = {case.id: case.says for case in CASES}
    assert "no benchmark" in says["mundo"]
    assert "not enough data" in says["viego"]


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
    # The tool results come before the reply, so calls on one answer share a cache.
    first, second = body["messages"][0]["content"]
    assert first["text"].startswith("<tool_results>")
    assert "<reply>\nReply\n</reply>" in second["text"]


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
    from eval.costs import PRICES

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
