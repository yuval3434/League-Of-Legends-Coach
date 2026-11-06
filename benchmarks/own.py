"""A player's own numbers in one role, for when no benchmark fits them yet.

Each of the role's measures over all their games, and over their wins and their
losses apart. Wins and losses go through the same gap and margin as a benchmark
comparison, so "clear" means the same thing everywhere. Nothing from anyone
else's games is used, and nothing stands in for a benchmark.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from analytics.stats import MIN_GAMES, Scope
from benchmarks.compare import ROLE_METRICS, _gap, _keyed

NOTE = (
    "Wins against losses shows how a measure relates to the result, not what "
    "caused it: a lead can win a game, and a winning game also builds a lead."
)


def _side(row: dict[str, Any] | None, value: str, sample: str) -> dict[str, Any]:
    if row is None:
        return {"value": None, "margin": None, "sample": 0, "low_sample": True}
    margin = "margin_" + value.removeprefix("avg_")
    return {
        "value": row.get(value),
        "margin": row.get(margin),
        "sample": row[sample],
        "low_sample": row[sample] < MIN_GAMES,
    }


async def own_numbers(session: AsyncSession, puuids: list[str], role: str) -> dict[str, Any]:
    """The role's measures over all games, wins and losses, with sample sizes."""
    absolute, relative = ROLE_METRICS[role]
    # Win rate split by result says nothing; every other measure can be.
    metrics = [m for m in absolute + relative if m.name != "win_rate"]
    rows = []
    for metric in metrics:
        sides = {
            name: _keyed(
                [r for r in await metric.stat(session, Scope(puuids=tuple(puuids), role=role, win=win))
                 if r.get("result", "all") == "all"],
                metric,
            )
            for name, win in (("all", None), ("wins", True), ("losses", False))
        }
        for key in sorted(sides["all"].keys(), key=str):
            for value in metric.values:
                if value.startswith("median_"):
                    continue
                wins, losses = sides["wins"].get(key), sides["losses"].get(key)
                enough = bool(losses) and losses[metric.sample] >= MIN_GAMES
                gap = _gap(value, wins, losses, enough)
                context = value in metric.context
                rows.append(
                    {
                        "metric": metric.name,
                        "theme": metric.theme,
                        "higher_is_better": metric.higher_is_better,
                        **dict(zip(metric.keys, key)),
                        "value": value,
                        "sample_unit": metric.sample,
                        "all": _side(sides["all"][key], value, metric.sample),
                        "wins": _side(wins, value, metric.sample),
                        "losses": _side(losses, value, metric.sample),
                        "difference": gap["difference"],
                        "difference_margin": gap["difference_margin"],
                        # Judged only with 10+ games on each side, like any comparison.
                        "clear_gap": None
                        if context or not wins or wins[metric.sample] < MIN_GAMES
                        else gap["clear_gap"],
                        **({"context_only": True} if context else {}),
                    }
                )
    return {"role": role, "rows": rows, "notes": [NOTE]}
