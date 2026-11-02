from agent.llm import Usage
from agent.pricing import answer_cost, cost

USAGE = Usage(input_tokens=1_000_000, output_tokens=100_000)


def test_one_model_prices_exactly():
    # Opus 5.5: $4 per million in, $20 per million out.
    assert cost(USAGE, "claude-opus-5-5") == 4.0 + 2.0
    assert answer_cost(USAGE, ["claude-opus-5-5", "claude-opus-5-5"]) == (6.0, False)


def test_a_fallback_prices_everything_at_the_dearest_model():
    # Opus and Sonnet both answered; the split isn't known, so Opus is the bound.
    assert answer_cost(USAGE, ["claude-opus-5-5", "claude-sonnet-5-5"]) == (6.0, True)


def test_an_unknown_model_gives_no_cost():
    assert answer_cost(USAGE, ["claude-opus-5-5", "mystery"]) == (None, False)
    assert answer_cost(USAGE, []) == (None, False)
