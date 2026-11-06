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


def first_try(answer: CoachAnswer) -> Check:
    """No number was caught, so the coach never tried a number of its own."""
    caught = answer.caught_numbers
    return Check(not caught, f"caught {caught}" if caught else "nothing caught")


def says(answer: CoachAnswer, phrases: tuple[str, ...]) -> Check:
    """The reply matches one of the patterns, ignoring case and curly quotes."""
    text = _normal(answer.text)
    found = [phrase for phrase in phrases if re.search(phrase, text)]
    return Check(bool(found), f"found {found}" if found else f"none of {list(phrases)}")


def right_cohort(answer: CoachAnswer, cohort: str | None) -> Check:
    """Every benchmark comparison used the player's own peer cohort, and there was one."""
    used = [log.arguments.get("cohort") for log in answer.tool_log if log.name == "compare_to_benchmark"]
    passed = bool(used) and cohort is not None and all(c == cohort for c in used)
    return Check(passed, f"compared with {used}, expected {cohort}")


def run_code_check(
    name: str, answer: CoachAnswer, phrases: tuple[str, ...], cohort: str | None = None
) -> Check:
    if name == "verified":
        return verified(answer)
    if name == "used_tools":
        return used_tools(answer)
    if name == "first_try":
        return first_try(answer)
    if name == "says":
        return says(answer, phrases)
    if name == "right_cohort":
        return right_cohort(answer, cohort)
    raise ValueError(f"Unknown code check: {name}")
