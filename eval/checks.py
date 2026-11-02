"""Checks done in code: exact, free and the same on every run."""

import re
from dataclasses import dataclass

from agent.coach import CoachAnswer

NUMBER_WORDS = re.compile(
    r"\b(zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|"
    r"forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|dozen|twice|"
    r"double|doubled|triple|tripled|half|halved|quarter|third|thirds)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Check:
    passed: bool
    detail: str


def number_words(text: str) -> list[str]:
    """Words that may state a quantity. The judge decides which ones do."""
    return sorted({match[0].lower() for match in NUMBER_WORDS.finditer(text)})


def _normal(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("’", "'")).lower()


def verified(answer: CoachAnswer) -> Check:
    """The number check passed, on the first try or after its retry."""
    return Check(answer.status == "verified", f"status {answer.status}")


def used_tools(answer: CoachAnswer) -> Check:
    return Check(bool(answer.tools_called), f"tools {answer.tools_called}")


def says(answer: CoachAnswer, phrases: tuple[str, ...]) -> Check:
    """The reply contains one of the phrases, ignoring case and curly quotes."""
    text = _normal(answer.text)
    found = [phrase for phrase in phrases if phrase in text]
    return Check(bool(found), f"found {found}" if found else f"none of {list(phrases)}")


def run_code_check(name: str, answer: CoachAnswer, phrases: tuple[str, ...]) -> Check:
    if name == "verified":
        return verified(answer)
    if name == "used_tools":
        return used_tools(answer)
    if name == "says":
        return says(answer, phrases)
    raise ValueError(f"Unknown code check: {name}")
