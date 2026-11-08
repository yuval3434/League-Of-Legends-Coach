"""Number citations: every number in a reply names the field it was copied from.

The server gives each JSON object in a tool result a `ref`, such as "2.14": the
call's number in the conversation, then the object's place in that result. The
model writes each number followed at once by [[ref.field]], or by [[tool_name]]
for a fixed fact in that tool's description. The server checks that the number
equals the field, exactly as written, and strips the markers before anyone
reads the reply.

This closes the gap the plain number check leaves: a number that exists
somewhere in the results, but not in the field the reply is about. It can't
catch a number from the right field used in a wrong sentence, such as "8 games
each" when only one of two splits has 8.
"""

import itertools
import json
import re
from dataclasses import dataclass, field
from typing import Any

from agent.numbers import ALLOWED_PHRASE, GAME_TIME, NUMBER, _value, _values, list_markers

MARKER = re.compile(r"\[\[([^\[\]\n]{1,80})\]\]")

# A minute label: "minute 15", "minutes 10 and 15", "15 minutes", "the 10-minute
# mark", "at 10, 15 and 20 min". Its numbers need no citation, but each must be a
# minute the results define (see minutes()).
# Whole numbers only: "21" in "21.8" isn't a minute.
_N = r"\d{1,3}(?!\d|\.\d)"
_LIST = rf"{_N}(?:\s*(?:,|and|or|to|-|–)\s*{_N})*"
MINUTE_LABEL = re.compile(
    rf"\bminutes?\s+{_LIST}\b|\b{_LIST}(?:\s+|-)(?:minutes?|mins?)\b", re.IGNORECASE
)
# The keys whose values are minutes, and stretch names such as "10-15".
MINUTE_KEYS = ("minute", "start_minute", "end_minute", "stretch")

# Fields that say which row an object is, for the hover's label.
IDENTIFYING = (
    "cohort",
    "champion",
    "role",
    "dimension",
    "metric",
    "value",
    "minute",
    "phase",
    "result",
    "objective",
    "stretch",
    "lane",
    "losses_before",
    "bucket",
)

PROMPT = """

Citations
Every number you write must be followed at once by a citation to the tool-result \
field it was copied from: the object's `ref` and the field's name, in double square \
brackets, such as 184[[2.14.my_value]] or 52.9[[1.3.win_rate_pct]]%. For a fixed fact \
in a tool's description, cite the tool's name, such as 30[[compare_to_benchmark]]. A \
number inside a note or a list cites that field, such as 30[[1.0.notes]]. Copy the \
value exactly as the field holds it; you may leave out a minus sign when the words \
say behind or ahead. Minute labels need no citation: "at minute 15", "15 minutes", \
"the 10-minute mark" and "15:00" are checked against the minutes in the results. \
Only those, list numbering and the phrase "1 in 20" need no citation, so don't \
write any other number of your own, even in a heading. The citations are removed before the player reads the reply: never mention \
them.\
"""

RETRY = (
    "An automatic check found problems with the citations of these numbers: "
    "{problems}. Every number must be followed by [[ref.field]] for the field it was "
    "copied from, and must equal that field exactly, with no rounding. Fix them, or "
    "rewrite those sentences without the numbers. Write it for the player: don't "
    "mention this check or what you changed."
)


def label(content: str, call: int) -> str:
    """The result with a `ref` first in every object; unchanged if it isn't JSON."""
    try:
        data = json.loads(content)
    except ValueError:
        return content
    places = itertools.count()

    def walk(value: Any) -> Any:
        if isinstance(value, dict):
            labelled = {"ref": f"{call}.{next(places)}"}
            labelled.update({key: walk(item) for key, item in value.items()})
            return labelled
        if isinstance(value, list):
            return [walk(item) for item in value]
        return value

    return json.dumps(walk(data), default=str)


@dataclass(frozen=True)
class Source:
    """One labelled tool result: which tool, its objects by ref, and where each
    object sits, for its label: its row's identifying fields and its side."""

    tool: str
    objects: dict[str, dict[str, Any]]
    contexts: dict[str, str] = field(default_factory=dict)


def _identifying(obj: dict[str, Any]) -> list[str]:
    # A side object's "value" is a measurement, not a name, so only text counts there.
    return [
        f"{k} {obj[k]}"
        for k in IDENTIFYING
        if obj.get(k) not in (None, "") and (k != "value" or isinstance(obj[k], str))
    ]


def sources(results: list[tuple[str, str]]) -> dict[str, Source]:
    """Each labelled result's objects, keyed by the call part of their refs."""
    found: dict[str, Source] = {}
    for tool, content in results:
        try:
            data = json.loads(content)
        except ValueError:
            continue
        objects: dict[str, dict[str, Any]] = {}
        contexts: dict[str, str] = {}

        def walk(value: Any, inherited: list[str], key: str | None) -> None:
            if isinstance(value, dict):
                # A nested object, such as a row's "losses" side, keeps its row's fields.
                parts = inherited + ([key] if key and key != "rows" else []) + _identifying(value)
                if "ref" in value:
                    objects[str(value["ref"])] = value
                    contexts[str(value["ref"])] = ", ".join(parts)
                for child_key, item in value.items():
                    walk(item, parts, child_key)
            elif isinstance(value, list):
                for item in value:
                    walk(item, inherited, key)

        walk(data, [], None)
        for ref in objects:
            found[ref.split(".")[0]] = Source(tool, objects, contexts)
            break
    return found


def minutes(found: dict[str, Source], descriptions: dict[str, str]) -> set[float]:
    """Every minute the results or descriptions define, for checking minute labels.
    Minute 0, the start of the game, always counts."""
    defined: set[float] = {0.0}
    for source in found.values():
        for obj in source.objects.values():
            for key in MINUTE_KEYS:
                if obj.get(key) is not None:
                    defined |= _values(str(obj[key]))
    for text in descriptions.values():
        defined |= {_value(m[1]) for m in GAME_TIME.finditer(text) if m[2] == "00"}
    return defined


@dataclass
class Citation:
    number: str
    target: str
    label: str


@dataclass
class Checked:
    """The reply without markers, the same with cited numbers as links, and what failed."""

    text: str
    linked: str
    citations: list[Citation] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def _describe(tool: str, context: str, name: str) -> str:
    return f"{tool}: {context + ' → ' if context else ''}{name}"


def _resolve(
    target: str,
    number: str,
    found: dict[str, Source],
    descriptions: dict[str, str],
) -> tuple[str | None, str]:
    """(problem or None, label) for one number and the target it cites."""
    written = _value(number)
    if target in descriptions:
        ok = written in _values(descriptions[target])
        return (None if ok else f"{number} isn't in {target}'s description"), f"{target}: tool description"
    parts = target.split(".")
    if len(parts) < 3 or parts[0] not in found:
        return f"{number} cites {target}, which isn't a field of any tool result", target
    source = found[parts[0]]
    ref, name = ".".join(parts[:2]), ".".join(parts[2:])
    obj = source.objects.get(ref)
    if obj is None or name not in obj:
        return f"{number} cites {target}, which isn't a field of any tool result", target
    value, where = obj[name], _describe(source.tool, source.contexts.get(ref, ""), name)
    if isinstance(value, bool) or value is None:
        return f"{number} cites {target}, which holds no number", where
    if isinstance(value, (int, float)):
        if abs(written) != abs(round(float(value), 6)):
            return f"{number} cites {target}, which is {value}", where
        return None, where
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    if written not in _values(text):
        return f"{number} cites {target}, which doesn't contain it", where
    return None, where


def check_citations(
    reply: str,
    results: list[tuple[str, str]],
    descriptions: dict[str, str],
    exempt: tuple[str, ...] = (),
) -> Checked:
    """Check every number's citation. `results` are (tool name, labelled content).

    `exempt` are strings whose digits need no citation, such as the player's Riot ID.
    """
    found = sources(results)
    markers = [m.span() for m in MARKER.finditer(reply)]
    skipped = markers + list_markers(reply)
    skipped += [m.span() for m in ALLOWED_PHRASE.finditer(reply)]
    for text in exempt:
        skipped += [m.span() for m in re.finditer(re.escape(text), reply)] if text else []

    def free(start: int, end: int, taken: list[tuple[int, int]]) -> bool:
        return all(end <= a or start >= b for a, b in taken)

    tokens: list[tuple[int, int, str, bool]] = []
    for m in GAME_TIME.finditer(reply):
        if free(*m.span(), skipped):
            tokens.append((m.start(), m.end(), m[0], True))
    times = [(s, e) for s, e, _, _ in tokens]
    for m in NUMBER.finditer(reply):
        if free(*m.span(), skipped + times):
            tokens.append((m.start(), m.end(), m[0], False))
    tokens.sort()
    labels = [m.span() for m in MINUTE_LABEL.finditer(reply)]
    defined = minutes(found, descriptions)

    checked = Checked("", "")
    plain, linked, last = [], [], 0
    for start, end, number, minute in tokens:
        cite = MARKER.match(reply, end)
        plain.append(reply[last:start])
        linked.append(reply[last:start])
        if cite is None:
            in_label = minute or not free(start, end, labels)
            value = _value(number.split(":")[0] if minute else number)
            if not in_label:
                checked.problems.append(f"{number} has no citation")
            elif value not in defined or (minute and not number.endswith(":00")):
                checked.problems.append(f"{number} isn't a minute any tool result defines")
            plain.append(number)
            linked.append(number)
            last = end
            continue
        target = cite[1].strip()
        value = number.split(":")[0] if minute else number
        problem, where = _resolve(target, value, found, descriptions)
        if minute and not number.endswith(":00"):
            problem = f"{number} isn't a whole minute"
        plain.append(number)
        if problem:
            checked.problems.append(problem)
            linked.append(number)
        else:
            linked.append(f"[{number}](cite:{len(checked.citations)})")
            checked.citations.append(Citation(number, target, where))
        last = cite.end()
    plain.append(reply[last:])
    linked.append(reply[last:])
    # A marker that follows no number is dropped too.
    checked.text = MARKER.sub("", "".join(plain))
    checked.linked = MARKER.sub("", "".join(linked))
    checked.problems = list(dict.fromkeys(checked.problems))
    return checked
