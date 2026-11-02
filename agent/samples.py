"""Sample sizes behind each tool call, worked out in code for the UI.

They come from the tool results themselves, so the user can see what an answer
rests on without trusting the model to report it.
"""

import json
from typing import Any

from agent.coach import ToolLog


def _games(rows: list[dict[str, Any]], key: str) -> dict[str, int] | None:
    values = [row[key] for row in rows if isinstance(row.get(key), int)]
    return {"min": min(values), "max": max(values)} if values else None


def summarize(log: ToolLog) -> dict[str, Any]:
    summary: dict[str, Any] = {"name": log.name, "arguments": log.arguments}
    if log.is_error:
        return summary | {"error": True}
    result = json.loads(log.content)
    if log.name == "data_coverage":
        return summary | {"your_games": {"min": result["player"]["games"], "max": result["player"]["games"]}}
    rows = result.get("rows", [])
    if log.name == "compare_to_benchmark":
        game_rows = [row for row in rows if row.get("sample_unit", "games") == "games"]
        return summary | {
            "status": result["status"],
            "your_games": _games(game_rows, "my_sample"),
            "benchmark_games": result["benchmark_games"],
            "benchmark_players": result["benchmark_players"],
        }
    return summary | {
        "your_games": _games(rows, "games"),
        "low_sample_rows": sum(1 for row in rows if row.get("low_sample")),
    }
