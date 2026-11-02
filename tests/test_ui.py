"""The UI's handling of API responses, against a fake API: no server, no browser."""

import httpx

from ui.app import (
    ALL_CHAMPIONS,
    GREY,
    NO_KEY,
    ask,
    build,
    champion_table,
    coverage,
    my_champions,
    stat,
    status_text,
    tools_table,
)

ANSWER = {
    "text": "You average 5.45 CS per minute.",
    "status": "verified",
    "caught_numbers": [],
    "tools": [
        {
            "name": "compare_to_benchmark",
            "arguments": {"cohort": "silver", "champion": None, "theme": None},
            "status": "ok",
            "your_games": {"min": 26, "max": 30},
            "benchmark_games": 500,
            "benchmark_players": 456,
        },
        {"name": "win_rates", "arguments": {"champion": "Viego"}, "your_games": {"min": 8, "max": 8}},
        {"name": "deaths_by_phase", "arguments": {"champion": None}, "error": True},
    ],
}


def client(status=200, body=None, fail=False):
    def handler(request):
        if fail:
            raise httpx.ConnectError("refused")
        return httpx.Response(status, json=body if body is not None else ANSWER)

    return httpx.Client(base_url="http://api", transport=httpx.MockTransport(handler))


def test_an_answer_shows_its_reply_status_and_tools():
    text, check, tools = ask("How's my farming?", client())
    assert text == ANSWER["text"]
    assert "Number check passed" in check
    assert tools.values.tolist() == [
        ["compare_to_benchmark", "cohort=silver", "26–30", "500 (456 players)"],
        ["win_rates", "champion=Viego", "8", ""],
        ["deaths_by_phase", "", "failed", ""],
    ]


def test_a_failed_check_names_the_numbers():
    assert "9999" in status_text({"status": "unverified", "caught_numbers": ["9999"]})


def test_no_key_says_clearly_that_the_coach_needs_one():
    text, check, _ = ask("Hi", client(503, {"detail": "ANTHROPIC_API_KEY is not set"}))
    assert text == NO_KEY
    assert "Stats" in text


def test_a_missing_api_is_explained():
    text, _, _ = ask("Hi", client(fail=True))
    assert "Can't reach the API" in text


def test_an_empty_question_isnt_sent():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=ANSWER)

    ask("   ", httpx.Client(base_url="http://api", transport=httpx.MockTransport(handler)))
    assert calls == []


def test_no_benchmark_is_shown_in_the_tools_table():
    tool = ANSWER["tools"][0] | {"status": "no_benchmark", "benchmark_games": 19, "benchmark_players": 16}
    assert tools_table([tool]).values.tolist()[0][3] == "19 (16 players): no benchmark"


def test_coverage_summarizes_the_data_and_lists_champions():
    body = {"player": {"games": 12, "jungle_games": 12, "first_game": "2026-01-05",
                       "last_game": "2026-01-20", "patches": ["16.1", "16.2"]},
            "champions": [{"champion": "Quinn", "games": 5}, {"champion": "Viego", "games": 1}]}
    summary, played = coverage(client(body=body))
    assert summary == (
        "**Your data:** 12 games, 12 in the jungle, from 2026-01-05 to 2026-01-20, "
        "patches 16.1 to 16.2."
    )
    assert played == ["Quinn", "Viego"]


def test_a_stat_flags_low_samples():
    body = {"rows": [{"value": "Viego", "games": 8, "low_sample": True}]}
    rows, note = stat("win_rates", "", client(body=body))
    assert rows.to_dict("records") == body["rows"]
    assert "not enough data" in note


def test_the_app_builds():
    assert build(client()) is not None


def recording_client(body):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=body)

    return httpx.Client(base_url="http://api", transport=httpx.MockTransport(handler)), requests


def test_all_champions_sends_no_filter():
    http, requests = recording_client({"rows": []})
    stat("win_rates", ALL_CHAMPIONS, http)
    stat("win_rates", "Viego", http)
    assert [dict(r.url.params) for r in requests] == [{}, {"champion": "Viego"}]


CHAMPIONS = [
    {"champion": "DrMundo", "games": 17, "wins": 9, "win_rate_pct": 52.9, "kda": 2.4, "cs_per_min": 5.1},
    {"champion": "Viego", "games": 8, "wins": 3, "win_rate_pct": 37.5, "kda": 2.06, "cs_per_min": 5.7},
]


def test_low_sample_rows_stay_visible_greyed_and_noted():
    styled = champion_table(CHAMPIONS)
    frame = styled.data
    assert frame["Champion"].tolist() == ["DrMundo", "Viego"]
    assert frame["Note"].tolist() == ["", "not enough data"]
    # The style computed for each cell: (row, column) -> [(property, value)].
    styles = styled._compute().ctx
    grey = ("color", GREY.split(": ")[1])
    columns = range(len(frame.columns))
    assert all(grey in styles[(1, c)] for c in columns)
    assert not any(grey in styles.get((0, c), []) for c in columns)


def test_a_role_maps_to_the_api_value():
    http, requests = recording_client({"rows": CHAMPIONS})
    my_champions("Support", http)
    my_champions("All", http)
    assert [dict(r.url.params) for r in requests] == [{"role": "UTILITY"}, {}]


def test_a_role_with_no_games_says_so():
    http, _ = recording_client({"rows": []})
    table, note = my_champions("Top", http)
    assert "No games in this role" in note
