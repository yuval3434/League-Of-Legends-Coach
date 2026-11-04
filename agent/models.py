"""The coach models a person can pick, and what a question costs on each.

The estimate is a measured token profile times each model's price, so it's
worked out in code, not typed in. Other models write more or fewer tokens than
Opus did, so it's an estimate, and the page says so.
"""

from dataclasses import dataclass

from agent.llm import Usage
from agent.pricing import cost

# The average coach answer in the live Opus eval of 2026-11-03 (8 answers): mostly
# tool results written to and read from the prompt cache. It cost $0.1047 on
# average, and this profile prices at $0.1048 on Opus.
TYPICAL_USAGE = Usage(input_tokens=6, output_tokens=1196, cache_read_tokens=5310, cache_write_tokens=15950)


@dataclass(frozen=True)
class Choice:
    id: str
    label: str
    provider: str  # "anthropic" or "ollama"


CHOICES = (
    Choice("claude-opus-5-5", "Opus 5.5", "anthropic"),
    Choice("claude-sonnet-5-5", "Sonnet 5.5", "anthropic"),
    Choice("claude-haiku-5-5", "Haiku 5.5", "anthropic"),
    Choice("local", "Local", "ollama"),
)
BY_ID = {choice.id: choice for choice in CHOICES}


def estimated_cost(choice_id: str) -> float:
    """Dollars for a typical question: $0 for the local model."""
    return round(cost(TYPICAL_USAGE, choice_id), 4)
