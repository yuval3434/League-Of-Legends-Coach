"""Decide which comparison gaps count as findings.

About 1 in 20 rows can look clear by chance, so a clear row isn't a finding on
its own. Rows are grouped into themes, and a theme gives a finding in a direction
when either:
- two different metrics are clear in that direction, or
- one gap is at least STRONG_GAP_MULTIPLE times its margin.

The same metric at another minute doesn't count as a second metric: gold at 20
includes gold at 10. Deaths in different phases do, because those windows don't
overlap. Rows split by win or loss are left out, and so are rows on fewer than
MIN_GAMES of the player's games.
"""

from typing import Any

from analytics.stats import Row

THEMES = ("economy", "vision", "deaths", "fights", "objectives")
EVIDENCE = (
    "metric",
    "value",
    "minute",
    "phase",
    "my_value",
    "my_sample",
    "benchmark_value",
    "benchmark_sample",
    "difference",
    "difference_margin",
    # Kept so a reader of a theme alone can see each row was clear.
    "clear_gap",
    "strong_gap",
)


def _metric(row: Row) -> tuple[str, Any]:
    return row["value"], row.get("phase")


def _direction(row: Row) -> str:
    ahead = (row["difference"] > 0) == row["higher_is_better"]
    return "ahead" if ahead else "behind"


def _evidence(row: Row) -> Row:
    return {key: row[key] for key in EVIDENCE if key in row}


def _no_verdict(rows: list[Row]) -> str:
    """Why a theme has nothing to judge, given its whole-game rows."""
    if not rows:
        return "no_margin"
    if all(row["status"] == "no_benchmark" for row in rows):
        return "no_benchmark"
    if all(row["my_low_sample"] for row in rows):
        return "not_enough_data"
    return "no_margin"


def _summarize(theme: str, rows: list[Row]) -> Row:
    if not rows:
        return {"theme": theme, "status": "not_comparable"}

    whole_games = [row for row in rows if row.get("result", "all") == "all"]
    usable = [
        row
        for row in whole_games
        if row["clear_gap"] is not None and not row["my_low_sample"]
    ]
    if not usable:
        return {"theme": theme, "status": _no_verdict(whole_games)}

    clear = [row for row in usable if row["clear_gap"]]
    findings = []
    for direction in ("behind", "ahead"):
        group = [row for row in clear if _direction(row) == direction]
        if len({_metric(row) for row in group}) >= 2:
            basis = "agreeing_metrics"
        elif any(row["strong_gap"] for row in group):
            basis = "strong_gap"
        else:
            continue
        findings.append(
            {
                "direction": direction,
                "basis": basis,
                "rows": [_evidence(row) for row in group],
            }
        )

    found = {finding["direction"] for finding in findings}
    watching = [_evidence(row) for row in clear if _direction(row) not in found]
    if findings:
        status = "finding"
    else:
        status = "worth_watching" if watching else "nothing_clear"
    return {
        "theme": theme,
        "status": status,
        "findings": findings,
        "worth_watching": watching,
    }


def summarize_themes(rows: list[Row]) -> list[Row]:
    """One summary per theme, in a fixed order."""
    return [
        _summarize(theme, [row for row in rows if row["theme"] == theme])
        for theme in THEMES
    ]
