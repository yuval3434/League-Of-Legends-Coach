"""Turn raw Riot JSON into table rows. Pure functions, no I/O."""

from datetime import UTC, datetime
from typing import Any

Row = dict[str, Any]

# Promoted to their own columns in timeline_events; the rest goes in `data`.
EVENT_COLUMN_FIELDS = {
    "timestamp",
    "type",
    "position",
    "killerId",
    "participantId",
    "creatorId",
    "victimId",
}


def _patch(game_version: str) -> str:
    """'14.20.123.456' -> '14.20'."""
    return ".".join(game_version.split(".")[:2])


def parse_match(raw: Row) -> tuple[Row, list[Row]]:
    """Return the `matches` row and the `match_participants` rows."""
    match_id = raw["metadata"]["matchId"]
    info = raw["info"]

    # gameDuration is in milliseconds on matches with no gameEndTimestamp.
    duration = info["gameDuration"]
    if "gameEndTimestamp" not in info:
        duration //= 1000

    match = {
        "match_id": match_id,
        "platform": info["platformId"],
        "queue_id": info["queueId"],
        "patch": _patch(info["gameVersion"]),
        "game_version": info["gameVersion"],
        "game_start_at": datetime.fromtimestamp(
            info.get("gameStartTimestamp", info["gameCreation"]) / 1000, UTC
        ),
        "duration_s": duration,
        "is_remake": any(
            p.get("gameEndedInEarlySurrender", False) for p in info["participants"]
        ),
    }
    participants = [
        {
            "match_id": match_id,
            "participant_id": p["participantId"],
            "puuid": p["puuid"],
            "team_id": p["teamId"],
            "team_position": p["teamPosition"],
            "champion_id": p["championId"],
            "champion_name": p["championName"],
            "win": p["win"],
            "kills": p["kills"],
            "deaths": p["deaths"],
            "assists": p["assists"],
            "lane_cs": p["totalMinionsKilled"],
            "jungle_cs": p["neutralMinionsKilled"],
            "gold_earned": p["goldEarned"],
            "damage_to_champions": p["totalDamageDealtToChampions"],
            "vision_score": p["visionScore"],
        }
        for p in info["participants"]
    ]
    return match, participants


def parse_timeline(raw: Row) -> tuple[list[Row], list[Row]]:
    """Return the `timeline_frames` rows and the `timeline_events` rows."""
    match_id = raw["metadata"]["matchId"]
    frames: list[Row] = []
    events: list[Row] = []

    for minute, frame in enumerate(raw["info"]["frames"]):
        for key, state in frame["participantFrames"].items():
            position = state.get("position", {})
            frames.append(
                {
                    "match_id": match_id,
                    "participant_id": int(key),
                    "minute": minute,
                    "timestamp_ms": frame["timestamp"],
                    "total_gold": state["totalGold"],
                    "xp": state["xp"],
                    "level": state["level"],
                    "lane_cs": state["minionsKilled"],
                    "jungle_cs": state["jungleMinionsKilled"],
                    "damage_to_champions": state.get("damageStats", {}).get(
                        "totalDamageDoneToChampions"
                    ),
                    "position_x": position.get("x"),
                    "position_y": position.get("y"),
                }
            )

        for event in frame["events"]:
            position = event.get("position", {})
            events.append(
                {
                    "match_id": match_id,
                    "event_index": len(events),
                    "timestamp_ms": event["timestamp"],
                    "type": event["type"],
                    # Riot uses 0 for "no player".
                    "actor_id": (
                        event.get("killerId")
                        or event.get("participantId")
                        or event.get("creatorId")
                        or None
                    ),
                    "victim_id": event.get("victimId") or None,
                    "position_x": position.get("x"),
                    "position_y": position.get("y"),
                    "data": {
                        k: v for k, v in event.items() if k not in EVENT_COLUMN_FIELDS
                    },
                }
            )

    return frames, events
