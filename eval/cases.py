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
    # The reply must contain one of these, compared in lower case.
    says: tuple[str, ...] = ()

    @property
    def code_checks(self) -> tuple[str, ...]:
        return ALWAYS_CODE + (("says",) if self.says else ())

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
        says=("no benchmark", "isn't a benchmark", "not a benchmark", "doesn't have a benchmark"),
    ),
    Case(
        "viego",
        "How is my Viego compared with Silver?",
        ("no_overclaim",),
        says=("not enough data",),
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
)
