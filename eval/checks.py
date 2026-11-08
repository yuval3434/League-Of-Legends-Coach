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
    """No number of the coach's own on the first try, even one the retry fixed.

    With citations, a caught problem can be a slip on a real number, such as a
    missing citation, which isn't what this checks. A problem counts only if its
    number is in no tool result or tool description: computed or invented.
    """
    from agent.numbers import check_numbers
    from agent.tools import tool_definitions

    outputs = [log.content for log in answer.tool_log if not log.is_error]
    outputs += [tool["description"] for tool in tool_definitions()]
    own = [c for c in answer.caught_numbers if check_numbers(c.split(" ")[0], outputs)]
    slips = len(answer.caught_numbers) - len(own)
    detail = f"own numbers {own}" if own else "no number of its own"
    return Check(not own, detail + (f"; {slips} citation slip(s) the retry fixed" if slips else ""))


def compares(answer: CoachAnswer, cohort: str, champion: str) -> Check:
    """The coach compared with `cohort` on `champion`."""
    calls = [log.arguments for log in answer.tool_log if log.name == "compare_to_benchmark"]
    found = any(c.get("cohort") == cohort and (c.get("champion") or "").lower() == champion.lower() for c in calls)
    return Check(found, f"compare_to_benchmark calls: {calls}")


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


# Tools that measure only jungle games, so they're wrong for any other role.
JUNGLE_ONLY = ("objective_control", "first_lane_kill")


def role_args(answer: CoachAnswer, role: str, main_role: str | None) -> Check:
    """Every role-taking tool call used `role`, and there was at least one.

    MAIN, or no role where null means the main role, counts as `main_role`; a
    null role that means every role doesn't count as `role`. A comparison must
    use a cohort in `role`, and a jungle-only tool fails outside the jungle.
    """
    from agent.tools import _BY_NAME, IN_ROLE, MAIN
    from benchmarks.cohorts import get_cohort

    wrong, used = [], 0
    for log in answer.tool_log:
        args = log.arguments
        if log.name in JUNGLE_ONLY and role != "JUNGLE":
            wrong.append(f"{log.name} is jungle-only")
            continue
        if log.name == "compare_to_benchmark":
            used += 1
            cohort = get_cohort(str(args.get("cohort")))
            if cohort is None or cohort.role != role:
                wrong.append(f"compare_to_benchmark(cohort={args.get('cohort')})")
            continue
        tool = _BY_NAME.get(log.name)
        if tool is None or "role" not in tool.properties:
            continue
        given = args.get("role")
        main = given == MAIN or (given is None and tool.properties["role"] is IN_ROLE)
        used += 1
        if (main_role if main else given) != role:
            wrong.append(f"{log.name}(role={given})")
    passed = used > 0 and not wrong
    return Check(passed, f"wrong: {wrong}" if wrong else f"{used} role-taking calls, all {role}")


def avoids(answer: CoachAnswer, patterns: tuple[str, ...]) -> Check:
    """The reply matches none of the patterns, ignoring case and curly quotes."""
    text = _normal(answer.text)
    found = [p for p in patterns if re.search(p, text)]
    return Check(not found, f"found {found}" if found else "none found")


def run_code_check(
    name: str,
    answer: CoachAnswer,
    phrases: tuple[str, ...],
    cohort: str | None = None,
    role: str | None = None,
    main_role: str | None = None,
    avoid: tuple[str, ...] = (),
    compared: tuple[str, str] | None = None,
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
    if name == "role_args":
        return role_args(answer, role, main_role)
    if name == "avoids":
        return avoids(answer, avoid)
    if name == "compares":
        return compares(answer, *compared)
    raise ValueError(f"Unknown code check: {name}")
