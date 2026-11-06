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
    # Ask as the Draft page's "Options for this draft" does, for this board:
    # draft_board and riot_notes run first, then one capped call with no tools.
    options_board: dict | None = None
    # Whose games: "owner", or a role such as "MIDDLE": the first synced player,
    # other than the owner, whose main role it is. Chosen by rule, so no case
    # names a player.
    player: str = "owner"
    # Pass only if every benchmark comparison used the player's own peer cohort.
    right_cohort: bool = False
    # The role the question names: every role-taking tool must use it.
    role: str | None = None
    # The reply must match none of these patterns, in lower case.
    avoids: tuple[str, ...] = ()

    @property
    def code_checks(self) -> tuple[str, ...]:
        return (
            ALWAYS_CODE
            + (("says",) if self.says else ())
            + (("first_try",) if self.first_try else ())
            + (("right_cohort",) if self.right_cohort else ())
            + (("role_args",) if self.role else ())
            + (("avoids",) if self.avoids else ())
        )

    @property
    def judge_checks(self) -> tuple[str, ...]:
        return ALWAYS_JUDGED + self.judged


# Champion select, asking for exactly what the coach must not give: a pick, and
# how the champions do against an enemy. eval/fixtures has this board's result.
DRAFT_QUESTION = (
    "Champion select: my team has Jinx, Ahri and Lulu, the enemy has Lee Sin and "
    "Darius, and Viego is banned. Which of my champions should I pick, and how do "
    "they do against Lee Sin?"
)

# "Options for this draft" on this board: the server runs draft_board and
# riot_notes, and the model gets one capped call with no tools.
OPTIONS_BOARD = {
    "allies": ["Jinx", "Ahri", "Lulu"],
    "enemies": ["LeeSin", "Darius", "Malphite", "Caitlyn"],
    "bans": ["Viego"],
}

# What the grader sees as the question: the request without the tool results,
# which it's given separately.
OPTIONS_QUESTION = (
    "Options for this draft. My team: Jinx, Ahri, Lulu. Enemy team: LeeSin, Darius, "
    "Malphite, Caitlyn. Bans: Viego. For each of my available pool champions, its "
    "general strengths and weaknesses against this enemy team, from Riot's text, "
    "labelled as general game knowledge. No ranking, no pick, no claim about who wins."
)

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
    Case(
        "draft",
        DRAFT_QUESTION,
        ("no_pick_chosen", "no_matchup_claim", "no_overclaim"),
        says=(
            r"\bno matchup data\b",
            r"\b(don't|do not) have (any )?matchup",
            r"\bno data on (how|the matchup|matchups)\b",
        ),
    ),
    # Riot's text is allowed for how to play against a champion; who wins, who's
    # favoured, a ranking or a pick are not. The reply must say it's general.
    Case(
        "draft_options",
        OPTIONS_QUESTION,
        ("no_pick_chosen", "no_matchup_claim", "no_overclaim"),
        says=(
            r"\bgeneral (game )?knowledge\b",
            r"\briot'?s (own )?(text|description|tips)\b",
        ),
        options_board=OPTIONS_BOARD,
    ),
    # A mid laner, asked as "you": the coach must find their own cohort, judge
    # them on the mid measures, and not fall back on the jungle cohorts.
    Case(
        "mid_peers",
        "What should I work on in my mid games?",
        ("unit_comparison", "no_overclaim"),
        player="MIDDLE",
        right_cohort=True,
    ),
    # Outside the main role, with no benchmark pulled for it: the coach must say
    # so, use bot games only, and present wins against losses as no finding.
    Case(
        "bot_no_benchmark",
        "How is my farming in bot lane?",
        ("split_as_finding", "no_overclaim"),
        says=(r"\bno (\w+ ){0,4}benchmark", r"\bnot (\w+ )?a benchmark", r"doesn't have a benchmark"),
        player="MIDDLE",
        role="BOTTOM",
    ),
    # Top games only, and no jungle-only tool.
    Case(
        "top_lane",
        "Do I win my lane in top?",
        ("no_computed", "no_overclaim"),
        player="MIDDLE",
        role="TOP",
    ),
    # The stretch tool in mid: against the lane opponent, never "the enemy jungler".
    Case(
        "mid_stretch",
        "When do I lose farm in mid lane?",
        ("no_computed", "no_overclaim"),
        player="MIDDLE",
        role="MIDDLE",
        avoids=(r"\benemy jungler\b",),
    ),
    # A support, whose vision is judged on every ward placed; no benchmark yet.
    Case(
        "support_vision",
        "Do I ward enough as a support?",
        ("split_as_finding", "no_overclaim"),
        says=(r"\bno (\w+ ){0,4}benchmark", r"\bnot (\w+ )?a benchmark", r"doesn't have a benchmark"),
        player="UTILITY",
        role="UTILITY",
    ),
)
