"""Replace every player's identity in raw Riot responses, for the public demo.

Fields are rewritten by name wherever they appear, because Riot repeats some of
them in unexpected places: the game ID is also in the timeline's GAME_END event.
`find_originals` then searches the result for every original value, so a field
this misses is caught rather than published.

Stats, champions and positions are kept. So someone who already knows the
player's Riot ID could still find these games by their stats.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

ME = "demo-jungler"
MY_NAME, TAG = "DemoJungler", "DEMO"
DEFAULT_ICON, DEFAULT_LEVEL = 29, 100
# Real-world clock times. Times inside a game count from its start and are kept.
CLOCK_KEYS = {
    "gameCreation",
    "gameStartTimestamp",
    "gameEndTimestamp",
    "realTimestamp",
    "actualStartTime",
}
DEMO_START = datetime(2026, 1, 5, 18, 0, tzinfo=UTC)


def demo_match_id(number: int) -> str:
    return f"DEMO1_{number:04d}"


@dataclass
class Anonymizer:
    """One per dataset, so a player in several matches keeps one demo identity."""

    my_puuid: str
    offset_ms: int
    puuids: dict[str, str] = field(default_factory=dict)

    def player(self, puuid: str) -> str:
        if puuid == self.my_puuid:
            return ME
        if puuid not in self.puuids:
            self.puuids[puuid] = f"demo-player-{len(self.puuids) + 1:03d}"
        return self.puuids[puuid]

    def _name(self, demo_puuid: str) -> str:
        return MY_NAME if demo_puuid == ME else f"Player {int(demo_puuid[-3:])}"

    def _value(self, key: str, value: Any, number: int, owner: str | None) -> Any:
        if key == "puuid":
            return self.player(value)
        if key in ("riotIdGameName", "summonerName"):
            return self._name(owner) if owner else ""
        if key == "riotIdTagline":
            return TAG
        if key == "summonerId":
            return f"demo-summoner-{owner}" if owner else ""
        if key == "profileIcon":
            return DEFAULT_ICON
        if key == "summonerLevel":
            return DEFAULT_LEVEL
        if key == "matchId":
            return demo_match_id(number)
        if key == "gameId":
            return number
        if key == "gameName":
            return "demo"
        if key == "tournamentCode":
            return ""
        if key in CLOCK_KEYS and isinstance(value, int):
            return value + self.offset_ms
        return self.walk(value, number)

    def walk(self, value: Any, number: int) -> Any:
        if isinstance(value, dict):
            owner = self.player(value["puuid"]) if isinstance(value.get("puuid"), str) else None
            return {k: self._value(k, v, number, owner) for k, v in value.items()}
        if isinstance(value, list):
            # metadata.participants is a bare list of PUUIDs.
            return [
                self.player(v) if isinstance(v, str) and len(v) > 40 else self.walk(v, number)
                for v in value
            ]
        return value


def offset_for(match_payloads: list[dict[str, Any]]) -> int:
    """Shift every game by one amount, so the first starts at DEMO_START."""
    first = min(m["info"]["gameStartTimestamp"] for m in match_payloads)
    return int(DEMO_START.timestamp() * 1000) - first


def originals(match: dict[str, Any], timeline: dict[str, Any], account: dict[str, Any]) -> set[Any]:
    """Every identifying value in one real match, to search the output for."""
    found: set[Any] = {match["metadata"]["matchId"], match["info"]["gameId"]}
    found |= set(match["metadata"]["participants"]) | set(timeline["metadata"]["participants"])
    for p in match["info"]["participants"]:
        for key in ("puuid", "summonerId", "riotIdGameName", "summonerName", "riotIdTagline"):
            if p.get(key):
                found.add(p[key])
    found |= {account["puuid"], account["gameName"], account["tagLine"]}
    return found


def champion_names(match_payloads: list[dict[str, Any]]) -> set[str]:
    return {p["championName"] for m in match_payloads for p in m["info"]["participants"]}


def find_originals(value: Any, banned: set[Any]) -> list[Any]:
    """Original values left in `value`, compared whole and as long substrings.

    Remove champion names from `banned` first: a player can be named after a
    champion, and the word appears in the data as the champion, not the player.
    """
    long_ids = [b for b in banned if isinstance(b, str) and len(b) >= 20]
    hits: list[Any] = []

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                visit(key)
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)
        elif isinstance(item, bool):
            return
        elif item in banned or (isinstance(item, str) and any(b in item for b in long_ids)):
            hits.append(item)

    visit(value)
    return hits
