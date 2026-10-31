"""Synthetic Riot responses, shaped like match-v5. Not real match data."""

from typing import Any


def make_match(match_id: str = "EUW1_1", queue: int = 420) -> dict[str, Any]:
    return {
        "metadata": {"matchId": match_id, "participants": []},
        "info": {
            "platformId": "EUW1",
            "queueId": queue,
            "gameVersion": "14.20.123.456",
            "gameCreation": 1_700_000_000_000,
            "gameStartTimestamp": 1_700_000_060_000,
            "gameEndTimestamp": 1_700_001_860_000,
            "gameDuration": 1800,
            "participants": [make_participant(i) for i in range(1, 11)],
        },
    }


def make_participant(participant_id: int) -> dict[str, Any]:
    return {
        "participantId": participant_id,
        "puuid": f"puuid-{participant_id}",
        "teamId": 100 if participant_id <= 5 else 200,
        "teamPosition": "TOP",
        "championId": 266,
        "championName": "Aatrox",
        "win": participant_id <= 5,
        "kills": 5,
        "deaths": 3,
        "assists": 7,
        "totalMinionsKilled": 180,
        "neutralMinionsKilled": 12,
        "goldEarned": 12000,
        "totalDamageDealtToChampions": 20000,
        "visionScore": 25,
        "gameEndedInEarlySurrender": False,
    }


def make_participant_frame() -> dict[str, Any]:
    return {
        "totalGold": 1500,
        "xp": 1200,
        "level": 4,
        "minionsKilled": 40,
        "jungleMinionsKilled": 2,
        "position": {"x": 1000, "y": 2000},
        "damageStats": {"totalDamageDoneToChampions": 800},
    }


def make_timeline(match_id: str = "EUW1_1") -> dict[str, Any]:
    states = {str(i): make_participant_frame() for i in range(1, 11)}
    return {
        "metadata": {"matchId": match_id},
        "info": {
            "frames": [
                {
                    "timestamp": 0,
                    "participantFrames": states,
                    "events": [
                        {"type": "PAUSE_END", "timestamp": 0, "realTimestamp": 1},
                    ],
                },
                {
                    "timestamp": 60_012,
                    "participantFrames": states,
                    "events": [
                        {
                            "type": "CHAMPION_KILL",
                            "timestamp": 45_000,
                            "killerId": 3,
                            "victimId": 7,
                            "position": {"x": 5000, "y": 6000},
                            "bounty": 300,
                        },
                        {
                            "type": "CHAMPION_KILL",
                            "timestamp": 50_000,
                            "killerId": 0,
                            "victimId": 2,
                        },
                        {
                            "type": "WARD_PLACED",
                            "timestamp": 55_000,
                            "creatorId": 4,
                            "wardType": "YELLOW_TRINKET",
                        },
                        {
                            "type": "ITEM_PURCHASED",
                            "timestamp": 58_000,
                            "participantId": 1,
                            "itemId": 1055,
                        },
                    ],
                },
            ]
        },
    }
