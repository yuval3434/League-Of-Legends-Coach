"""How long a pull will take, from the rates our own pulls measured.

Both rates come from real runs under a development key, 100 calls per 2 minutes:
- Up to 500 games: the Gold mid pull, on 2026-11-06, the first made from the
  Overview's offer, sampled 500 games from 653 checked matches in 29 minutes.
  The first Silver jungle pull took 91 minutes for 683 matches, but it shared
  the call budget with the Emerald pull running beside it.
- Past 500, only target champions are wanted, so other players are skipped
  without a rank check: the Emerald Dr. Mundo pull, on 2026-11-06, checked
  3,584 matches in 75 minutes.

A new cohort may start on stored lobbies, which skip the match call. That should
be faster, but no pull has measured it yet, so the estimate doesn't count on it.
"""

from benchmarks.cohorts import TARGET_OVERALL

# (games sampled, matches checked, minutes) up to 500, and (matches, minutes) past it.
TO_500_SAMPLED, TO_500_CHECKED, TO_500_MINUTES = 500, 653, 29
PAST_500_CHECKED, PAST_500_MINUTES = 3584, 75

# "Pull more" checks this many more matches, for champion benchmarks.
PULL_MORE_MATCHES = 2000
# A pull to 500 stops at this many times the matches it expects to need, in case
# a rank or role turns up less often than Silver junglers did.
SAFETY_MULTIPLE = 3


def to_500(overall_games: int) -> dict[str, int]:
    """Matches and minutes to bring the all-champion sample to TARGET_OVERALL."""
    needed = max(TARGET_OVERALL - overall_games, 0)
    matches = _ceil(needed * TO_500_CHECKED, TO_500_SAMPLED)
    return {
        "games_needed": needed,
        "matches": matches,
        "minutes": _ceil(matches * TO_500_MINUTES, TO_500_CHECKED),
    }


def pull_more() -> dict[str, int]:
    """Matches and minutes for one "Pull more"."""
    return {
        "matches": PULL_MORE_MATCHES,
        "minutes": _ceil(PULL_MORE_MATCHES * PAST_500_MINUTES, PAST_500_CHECKED),
    }


def _ceil(numerator: int, denominator: int) -> int:
    """Whole-number division rounded up, with no floating-point error."""
    return -(-numerator // denominator)
