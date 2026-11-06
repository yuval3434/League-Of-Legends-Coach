"""Replies with known verdicts, to measure the judge before trusting it.

Each bad reply plants one error into a real coach reply, so the only thing that
changes is the property being tested. Every label is meant to be clear-cut: a
borderline case would measure the labeller, not the judge.

The replies' vision passages were rewritten by hand when wards placed was split
into control and trinket wards (see DECISIONS.md): the originals called a gap a
finding that the split showed was trinket choice. Their numbers come from the
recaptured tool results; everything else is the coach's own text.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from eval.cases import DRAFT_QUESTION, OPTIONS_QUESTION

FIXTURES = Path(__file__).parent / "fixtures"


@dataclass(frozen=True)
class Example:
    id: str
    criterion: str
    question: str
    reply: str
    expected_pass: bool
    # Which saved set of tool results the reply is graded against.
    context: str = "work_on"


def _replace(text: str, old: str, new: str) -> str:
    assert text.count(old) == 1, f"calibration anchor not found once: {old!r}"
    return text.replace(old, new)


def load_examples() -> list[Example]:
    replies = json.loads((FIXTURES / "replies.json").read_text(encoding="utf-8"))
    farming, work_on = replies["farming"], replies["work_on"]
    r1, q1 = farming["text"], farming["question"]
    r2, q2 = work_on["text"], work_on["question"]
    r3, q3 = replies["deaths"]["text"], replies["deaths"]["question"]
    emerald_q = "Do I win my jungle matchup as well as Emerald junglers do?"
    wins_q = "How do my wins compare with my losses?"
    weakest_q = "What is my single weakest area?"
    stretch_q = "How much gold do I lose to the enemy jungler between minutes 10 and 15?"
    draft_q = DRAFT_QUESTION
    draft_shown = (
        "Your team (Jinx, Ahri, Lulu) has no frontline: no Tank, and fewer than two "
        "Fighters. From your jungle champions, Dr. Mundo adds one (17 games, 52.9% "
        "win rate, give or take 24.5). Shen, Nunu, Amumu, Volibear, Xin Zhao and Zac "
        "also add one, but each has under 10 games, so it's too early to tell how you "
        "do on them. "
        "There's no matchup data, so I can't say how any of them does against Lee Sin "
        "or Darius. The pick is yours."
    )
    options_q = OPTIONS_QUESTION
    options_shown = (
        "All of this is general game knowledge from Riot's text, not from your games.\n\n"
        "Dr. Mundo (17 games): his passive resists the first immobilizing effect that "
        "hits him, and his ultimate heals part of his missing health, so he can stay in "
        "long fights. Against Lee Sin, Riot's tip is to stay spread out to limit his "
        "ultimate, Dragon's Rage.\n\n"
        "Shen (7 games, too early to tell how you do on him): his ultimate shields an "
        "ally anywhere on the map. Against Darius, Riot says he's open to harassment "
        "while his axe grab is on cooldown, so that's the moment to trade.\n\n"
        "The pick is yours."
    )
    bucket = json.loads(load_tool_outputs("wins")[1]["content"])["rows"][0]
    buckets = (
        "Win rate by gold difference with the enemy jungler at {minute} minutes: "
        f"{bucket['bucket']}, {bucket['win_rate_pct']}% ({bucket['wins']} of "
        f"{bucket['games']} games)."
    )

    def ex(id, criterion, reply, expected_pass, question=q2, context="work_on"):
        return Example(id, criterion, question, reply, expected_pass, context)

    return [
        # A real number on the wrong stat.
        ex("real_farming_numbers", "wrong_stat", r1, True, q1),
        ex("real_work_on_numbers", "wrong_stat", r2, True),
        ex(
            "sides_swapped",
            "wrong_stat",
            _replace(r2, "you average 5.45, Silver averages 6.27", "you average 6.27, Silver averages 5.45"),
            False,
        ),
        ex(
            "emerald_called_silver",
            "wrong_stat",
            _replace(
                r2,
                "Against Emerald, your target, it's bigger still: their CS per minute is 6.83 (500 games).",
                "Silver junglers average 6.83 CS per minute (500 games).",
            ),
            False,
        ),
        ex(
            "wrong_minute",
            "wrong_stat",
            _replace(r1, "| CS at 15 min | 88.5 (29 games)", "| CS at 15 min | 112.4 (29 games)"),
            False,
            q1,
        ),
        # Numbers in words.
        ex("counts_its_own_advice", "number_words", r2, True),
        ex(
            "twice_as_many",
            "number_words",
            r2 + "\n\nYou place twice as many control wards as Silver junglers.",
            False,
        ),
        ex(
            "thirty_games",
            "number_words",
            _replace(r2, "use 30 of your recent jungle games", "use thirty of your recent jungle games"),
            False,
        ),
        ex(
            "half_the_rate",
            "number_words",
            r2 + "\n\nSilver junglers place about half as many control wards as you.",
            False,
        ),
        # Ranking gaps in different units.
        ex("biggest_gap", "unit_comparison", r2, False),
        ex("same_stat_over_time", "unit_comparison", r1, True, q1),
        ex(
            "weakest_area",
            "unit_comparison",
            r1 + "\n\nVision is your strongest area overall.",
            False,
            q1,
        ),
        # Win-only or loss-only rows presented as findings.
        ex("no_split_rows", "split_as_finding", r2, True),
        ex(
            "win_rows_as_finding",
            "split_as_finding",
            r2
            + "\n\nYour clearest finding is in the games you win: at 20 minutes you're "
            "14.1 CS behind, while Silver junglers are 9.1 ahead (227 games).",
            False,
        ),
        # Claiming more than the tool supports.
        ex("honest_strengths", "no_overclaim", r2, True),
        ex(
            "deaths_called_finding",
            "no_overclaim",
            _replace(
                r2,
                "- **Deaths:** no clear difference in the early, mid or late game. "
                "For example, early deaths are 2.23 for you vs 2.22 for Silver.",
                "- **Deaths:** a clear finding: you die more in the early game, "
                "2.23 for you vs 2.22 for Silver.",
            ),
            False,
        ),
        ex(
            "watching_called_proven",
            "no_overclaim",
            _replace(r2, "That might be a strength, but it could be chance.", "That's a proven strength."),
            False,
        ),
        # Reaching both findings.
        ex("both_findings", "findings_covered", r2, True),
        # Drops wards everywhere: an earlier version kept them in the opening line,
        # and the judge was right to pass it.
        ex(
            "only_farming",
            "findings_covered",
            _replace(
                r2.split("**2. Vision")[0],
                "I'd work on **farming**, and keep doing what you do for **vision**. Those "
                "are the only two areas where your numbers clearly differ from Silver "
                "junglers: you're behind on farming and ahead on vision.",
                "I'd work on one thing: **farming**. That's the only area where your "
                "numbers clearly differ from Silver junglers.",
            ),
            False,
        ),
        ex("empty_reply", "findings_covered", "", False),
        ex("no_answer", "findings_covered", "I don't know.", False),
        # Relative stats against Emerald.
        ex(
            "emerald_gold_difference",
            "not_comparable_respected",
            "Against Emerald junglers, your gold difference at 20 minutes is -599, "
            "so you lose your matchup more than they do.",
            False,
            emerald_q,
        ),
        ex(
            "emerald_declined",
            "not_comparable_respected",
            "Gold difference can't be compared with Emerald, because Emerald junglers "
            "face Emerald opponents. Against Silver, your gold difference at 20 minutes "
            "is -599 (26 games).",
            True,
            emerald_q,
        ),
        # Shapes the judge got wrong in the first live run. Each is the honest
        # version, so it must pass, beside a planted error where one fits.
        ex(
            "fact_from_tool_description",
            "wrong_stat",
            buckets.format(minute=10),
            True,
            wins_q,
            "wins",
        ),
        ex(
            "wrong_minute_for_buckets",
            "wrong_stat",
            buckets.format(minute=20),
            False,
            wins_q,
            "wins",
        ),
        ex(
            "boundary_from_uncalled_tool",
            "wrong_stat",
            "Early game (before 15:00): you average 2.23 deaths (30 games), and Silver "
            "averages 2.22 (500 games).",
            True,
            q3,
            "deaths_theme_only",
        ),
        ex(
            "wrong_boundary",
            "wrong_stat",
            "Early game (before 10:00): you average 2.23 deaths (30 games), and Silver "
            "averages 2.22 (500 games).",
            False,
            q3,
            "deaths_theme_only",
        ),
        ex(
            "vague_words",
            "number_words",
            r1 + "\n\nSeveral stats agree: you're a little behind at 10 minutes, but much "
            "further behind by 20.",
            True,
            q1,
        ),
        ex("grouped_against_no_gap", "unit_comparison", r3, True, q3, "deaths"),
        ex(
            "findings_cant_be_ranked",
            "unit_comparison",
            "Your findings can't be ranked on one scale, because they're measured in "
            "different units. Both are findings against Silver: farming, where you're "
            "behind (5.45 CS per minute against 6.27), and vision, where you're ahead "
            "(0.063 control wards a minute against 0.027).",
            True,
            weakest_q,
        ),
        ex("findings_from_one_theme", "no_overclaim", r3, True, q3, "deaths"),
        ex(
            "split_rows_as_suggestion",
            "split_as_finding",
            "In wins you're 14.1 CS behind the enemy jungler at 20 minutes (11 games), "
            "and in losses 25.7 behind (15 games). That might mean farm slips most in "
            "losses, but it's a suggestion, not a finding.",
            True,
            wins_q,
        ),
        ex(
            "split_rows_as_fact",
            "split_as_finding",
            "In wins you're 14.1 CS behind the enemy jungler at 20 minutes (11 games), "
            "and in losses 25.7 behind (15 games). So you lose because you stop farming "
            "when you fall behind.",
            False,
            wins_q,
        ),
        # Asked for a stretch with no stretch tool: the gaps at 10 and 15 are in
        # lane_diff, but anything between them would be the coach's own sum.
        ex(
            "stretch_not_available",
            "no_computed",
            "I don't have how much gold you lose between minutes 10 and 15. What I have: "
            "at 10 minutes you're 219 gold behind the enemy jungler (85 games), and at "
            "15 minutes 461 behind (84 games), so the gap is bigger at 15.",
            True,
            stretch_q,
            "wins",
        ),
        ex(
            "stretch_subtracted",
            "no_computed",
            "At 10 minutes you're 219 gold behind the enemy jungler (85 games), and at 15 "
            "minutes 461 behind (84 games), so you lose about 242 gold between 10 and 15.",
            False,
            stretch_q,
            "wins",
        ),
        ex(
            "stretch_in_words",
            "no_computed",
            "At 10 minutes you're 219 gold behind the enemy jungler (85 games), and at 15 "
            "minutes 461 behind (84 games): the gap roughly doubles between 10 and 15.",
            False,
            stretch_q,
            "wins",
        ),
        ex(
            "stretches_compared",
            "no_computed",
            "At 10 minutes you're 219 gold behind the enemy jungler (85 games), and at 15 "
            "minutes 461 behind (84 games), so you lose more gold between 10 and 15 than "
            "in the first 10 minutes.",
            False,
            stretch_q,
            "wins",
        ),
        # Champion select: show the options, never choose one or guess a matchup.
        ex("draft_shown", "no_pick_chosen", draft_shown, True, draft_q, "draft"),
        ex(
            "draft_pick_named",
            "no_pick_chosen",
            draft_shown + " Pick Dr. Mundo: he has the most games.",
            False,
            draft_q,
            "draft",
        ),
        ex(
            "draft_leaning",
            "no_pick_chosen",
            draft_shown + " If it were me, I'd lean towards Shen.",
            False,
            draft_q,
            "draft",
        ),
        ex(
            "draft_ranked",
            "no_pick_chosen",
            "Your team has no frontline. Your best options, in order: Dr. Mundo, "
            "Shen, then Nunu.",
            False,
            draft_q,
            "draft",
        ),
        ex("draft_no_matchup", "no_matchup_claim", draft_shown, True, draft_q, "draft"),
        ex(
            "draft_matchup_guess",
            "no_matchup_claim",
            draft_shown + " Dr. Mundo is a safe pick into Lee Sin.",
            False,
            draft_q,
            "draft",
        ),
        ex(
            "draft_matchup_as_advice",
            "no_matchup_claim",
            draft_shown + " General advice, not from your data: Lee Sin is strong early "
            "against tanks, so expect him to invade.",
            False,
            draft_q,
            "draft",
        ),
        # Options for this draft: how to play against a champion, from Riot's text,
        # is allowed; who wins, who's favoured or who's a good pick into whom isn't.
        ex("options_shown", "no_matchup_claim", options_shown, True, options_q, "options"),
        ex("options_shown_no_pick", "no_pick_chosen", options_shown, True, options_q, "options"),
        ex(
            "options_riot_weakness",
            "no_matchup_claim",
            options_shown + " Riot's text also says Lee Sin is vulnerable to magic damage.",
            True,
            options_q,
            "options",
        ),
        ex(
            "options_weakness_turned_into_a_pick",
            "no_matchup_claim",
            options_shown + " Riot's text says Lee Sin is vulnerable to magic damage, so "
            "your magic damage champions like Dr. Mundo do well against him.",
            False,
            options_q,
            "options",
        ),
        ex(
            "options_who_wins",
            "no_matchup_claim",
            options_shown + " In a long fight, Dr. Mundo beats Darius.",
            False,
            options_q,
            "options",
        ),
        ex(
            "options_good_pick_into",
            "no_matchup_claim",
            options_shown + " That makes Shen a good pick into Lee Sin.",
            False,
            options_q,
            "options",
        ),
        ex(
            "options_strongest",
            "no_pick_chosen",
            options_shown + " Of these, Dr. Mundo is your strongest option.",
            False,
            options_q,
            "options",
        ),
    ]


def load_tool_outputs(context: str = "work_on") -> list[dict]:
    saved = json.loads((FIXTURES / "tool_outputs.json").read_text(encoding="utf-8"))
    return saved[context]
