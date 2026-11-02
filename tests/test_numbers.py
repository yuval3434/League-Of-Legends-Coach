"""The number check, on replies a model could really write."""

import json

import pytest

from agent.numbers import check_numbers

RESULT = json.dumps(
    {
        "deaths_per_10_min": 2.7,
        "difference": -158.0,
        "games": 30,
        "my_value": 3584.0,
        "note": "The benchmark covers patches 16.20, 16.21.",
        "win_rate_pct": 46.7,
        "minute": 15,
    }
)


def unsupported(reply, outputs=(RESULT,)):
    return check_numbers(reply, list(outputs))


@pytest.mark.parametrize(
    "reply",
    [
        "Your gold at 15 is fine.",
        "You win 46.7% of 30 games.",
        "You average 3584 gold.",
        "You average 3,584 gold.",
        "You're 158 behind.",
        "You're -158 behind.",
        "Patch 16.21 is the latest.",
        "Your wins sit at 46.7.",
        "By 15:00 you're behind.",
        "Across 30, 15 and 30 games.",
    ],
)
def test_numbers_from_a_result_pass(reply):
    assert unsupported(reply) == []


@pytest.mark.parametrize(
    ("reply", "caught"),
    [
        ("You average 7.91 CS a minute.", ["7.91"]),
        ("You win about 47% of games.", ["47"]),
        ("You average roughly 3,600 gold.", ["3,600"]),
        ("That's 12 games.", ["12"]),
        ("You're 158 behind on 31 games.", ["31"]),
        ("That's .5 more.", [".5"]),
        ("By 14:30 you're behind.", ["14:30"]),
        ("By 25:00 you're behind.", ["25:00"]),
    ],
)
def test_numbers_not_in_a_result_are_caught(reply, caught):
    assert unsupported(reply) == caught


def test_a_reply_that_skipped_the_tools_has_no_support():
    assert unsupported("You win 46.7% of games.", outputs=[]) == ["46.7"]


def test_a_sum_the_model_worked_out_is_caught():
    # 3584 - 158 = 3426, which is true but isn't from a tool.
    assert unsupported("So the benchmark is 3426.") == ["3426"]


def test_each_number_is_reported_once():
    assert unsupported("99 and 99 again.") == ["99"]


def test_numbers_can_come_from_any_result():
    assert unsupported("7 and 8.", outputs=['{"a": 7}', '{"b": 8}']) == []


def test_a_digit_inside_a_key_doesnt_count_as_a_number():
    assert unsupported("You die 10 times.", outputs=['{"deaths_per_10_min": 2}']) == ["10"]


@pytest.mark.parametrize(
    "reply",
    ["1. Farm more\n2. Ward more\n3. Die less", "  1) Farm more", "About 1 in 20 rows."],
)
def test_list_numbers_and_the_prompt_phrase_are_exempt(reply):
    assert unsupported(reply, outputs=[]) == []


def test_a_list_number_is_still_checked_inside_the_line():
    assert unsupported("1. You died 9 times.", outputs=[]) == ["9"]


def test_digits_inside_words_are_ignored():
    assert unsupported("Season S14 and Q1.", outputs=[]) == []
