"""Questions for the live eval, with the checks each answer gets.

Code checks run on every answer that isn't refused, cut off or abandoned. Judge
checks are graded by a model. `number_words` is both: code finds candidate words,
and only an answer that has some goes to the judge.
"""

from dataclasses import dataclass

ALWAYS_CODE = ("verified", "used_tools")
ALWAYS_JUDGED = ("wrong_stat", "number_words")


@dataclass(frozen=True)
class Case:
    id: str
    question: str
    judged: tuple[str, ...] = ()
    # The reply must match one of these patterns, in lower case.
    says: tuple[str, ...] = ()
    # Tools the coach doesn't get for this question.
    hidden_tools: tuple[str, ...] = ()
    # Pass only if the number check caught nothing, even a number the retry fixed.
    first_try: bool = False

    @property
    def code_checks(self) -> tuple[str, ...]:
        return (
            ALWAYS_CODE
            + (("says",) if self.says else ())
            + (("first_try",) if self.first_try else ())
        )

    @property
    def judge_checks(self) -> tuple[str, ...]:
        return ALWAYS_JUDGED + self.judged


CASES = (
    Case(
        "farming",
        "How is my farming compared with Silver?",
        ("unit_comparison", "split_as_finding", "no_overclaim"),
    ),
    Case(
        "work_on",
        "What should I work on to win more games?",
        ("unit_comparison", "split_as_finding", "no_overclaim", "findings_covered"),
    ),
    Case(
        "mundo",
        "How do I play Dr. Mundo compared with Silver junglers?",
        ("no_overclaim",),
        says=(r"\bno (\w+ ){0,2}benchmark", r"\bnot (\w+ )?a benchmark", r"doesn't have a benchmark"),
    ),
    Case(
        "viego",
        "How is my Viego compared with Silver?",
        ("no_overclaim",),
        says=(r"not enough data",),
    ),
    Case(
        "deaths",
        "Do I die too much compared with Silver?",
        ("unit_comparison", "no_overclaim"),
    ),
    Case(
        "wins",
        "How do my wins compare with my losses?",
        ("split_as_finding", "no_overclaim"),
    ),
    Case(
        "emerald_lane",
        "Do I win my jungle matchup as well as Emerald junglers do?",
        ("not_comparable_respected", "no_overclaim"),
    ),
    Case(
        "weakest",
        "What is my single weakest area?",
        ("unit_comparison", "no_overclaim"),
    ),
    # Without farm_by_stretch, the only way to a per-stretch number is to subtract
    # lane_diff's minutes, which average over different games: 461 - 219 = 242
    # gold, when the stretch tool says 234. The coach must say it doesn't have it.
    Case(
        "stretch_no_tool",
        "How much gold do I lose to the enemy jungler between minutes 10 and 15?",
        ("no_computed", "no_overclaim"),
        says=(
            r"\bdon't have\b",
            r"\bdoesn't (have|give|show|include)\b",
            r"\b(can't|cannot) (give|tell|say|work out|calculate|compute)\b",
            r"\bisn't (in|available)\b",
            r"\bnot (in|available)\b",
        ),
        hidden_tools=("farm_by_stretch",),
        first_try=True,
    ),
)
