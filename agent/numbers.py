"""Check that every number in a reply appears in a tool result.

This catches invented numbers, rounded ones, sums the model worked out itself, and
answers that skipped the tools. It can't tell if a real number is attached to the
wrong stat, and it doesn't read numbers written as words, such as "twice".
"""

import re

NUMBER = re.compile(r"(?<![\w.])(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)")
# Not followed by a digit or ":digit" (so 1:23:45 isn't one), but a colon may end it: "15:00:".
GAME_TIME = re.compile(r"(?<![\w.:])(\d{1,3}):(\d{2})(?!\d)(?!:\d)")
LIST_MARKER = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)
# "1) CSing, 2) warding" inside a sentence. Only ")" counts, since "12. Then" can
# end a sentence, and only as a run 1), 2), ... on one line, since "(about 3) times"
# is a real number.
INLINE_MARKER = re.compile(r"(?<![\w.,(])(\d{1,2})\)(?=\s)")
# The system prompt tells the model to explain findings with this phrase.
ALLOWED_PHRASE = re.compile(r"\b1 in 20\b", re.IGNORECASE)


def list_markers(text: str) -> list[tuple[int, int]]:
    """Where the list numbering is: at a line's start, or an inline run 1), 2), ..."""
    spans = [m.span() for m in LIST_MARKER.finditer(text)]
    offset = 0
    for line in text.splitlines(keepends=True):
        run = []
        for m in INLINE_MARKER.finditer(line):
            if int(m[1]) == len(run) + 1:
                run.append((offset + m.start(), offset + m.end()))
        # A lone "1)" isn't a list; two in order are.
        if len(run) >= 2:
            spans += run
        offset += len(line)
    return sorted(set(spans))


def _blank(text: str, spans: list[tuple[int, int]]) -> str:
    for start, end in sorted(spans, reverse=True):
        text = text[:start] + " " + text[end:]
    return text


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
    text = ALLOWED_PHRASE.sub(" ", _blank(reply, list_markers(reply)))

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
