"""Check that every number in a reply appears in a tool result.

This catches invented numbers, rounded ones, sums the model worked out itself, and
answers that skipped the tools. It can't tell if a real number is attached to the
wrong stat, and it doesn't read numbers written as words, such as "twice".
"""

import re

NUMBER = re.compile(r"(?<![\w.])(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)")
GAME_TIME = re.compile(r"(?<![\w.:])(\d{1,3}):(\d{2})(?![\d:])")
LIST_MARKER = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)
# The system prompt tells the model to explain findings with this phrase.
ALLOWED_PHRASE = re.compile(r"\b1 in 20\b", re.IGNORECASE)


def _value(number: str) -> float:
    return round(float(number.replace(",", "")), 6)


def _values(text: str) -> set[float]:
    return {_value(match[0]) for match in NUMBER.finditer(text)}


def check_numbers(reply: str, tool_outputs: list[str]) -> list[str]:
    """Return the numbers in `reply` that no tool output contains, as written.

    A sign doesn't matter, so -158 in a result supports "158 behind". Tool outputs
    are read as plain text, so numbers in notes and patch names count too.
    """
    allowed = set().union(*map(_values, tool_outputs))
    text = ALLOWED_PHRASE.sub(" ", LIST_MARKER.sub(" ", reply))

    missing = []

    def check_time(match: re.Match[str]) -> str:
        # A game time like 15:00 is supported by the minute 15 in a result.
        if match[2] != "00" or _value(match[1]) not in allowed:
            missing.append(match[0])
        return " "

    text = GAME_TIME.sub(check_time, text)
    missing += [
        match[0] for match in NUMBER.finditer(text) if _value(match[0]) not in allowed
    ]
    return list(dict.fromkeys(missing))
