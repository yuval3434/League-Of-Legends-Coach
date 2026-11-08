"""Number citations: labelling results, checking each cited number, and replays of
the two recorded errors the plain number check let through."""

import json

from agent.citations import check_citations, label

DESCRIPTIONS = {"deaths_by_phase": "Deaths in the early (before 15:00), mid and late game."}


def labelled(tool, data, call=1):
    return tool, label(json.dumps(data), call)


def ref_of(source, **match):
    """The ref of the first object in a labelled result with these fields."""
    found = []

    def walk(value):
        if isinstance(value, dict):
            if all(value.get(k) == v for k, v in match.items()):
                found.append(value["ref"])
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(json.loads(source[1]))
    return found[0]


def check(reply, *results, exempt=()):
    return check_citations(reply, list(results), DESCRIPTIONS, exempt)


# Labelling


def test_every_object_gets_a_ref_first_numbered_by_call_and_place():
    _, content = labelled("lane_diff", {"rows": [{"minute": 10, "games": 92}, {"minute": 15, "games": 91}]}, call=3)
    data = json.loads(content)
    assert data["ref"] == "3.0"
    assert [row["ref"] for row in data["rows"]] == ["3.1", "3.2"]
    assert list(data["rows"][0])[0] == "ref"


def test_a_result_that_isnt_json_is_left_alone():
    assert label("There is no tool called x.", 1) == "There is no tool called x."


# Checking


ROWS = labelled("lane_diff", {"rows": [{"minute": 10, "avg_gold_diff": -184, "games": 92, "margin_gold_diff": 112}]})


def test_a_cited_number_that_equals_its_field_passes_and_the_markers_go():
    result = check("You're 184[[1.1.avg_gold_diff]] gold behind over 92[[1.1.games]] games.", ROWS)
    assert result.problems == []
    assert result.text == "You're 184 gold behind over 92 games."
    assert result.linked == "You're [184](cite:0) gold behind over [92](cite:1) games."
    assert result.citations[0].label == "lane_diff: minute 10 → avg_gold_diff"


def test_a_rounded_number_fails_even_though_it_is_close():
    result = check("A margin of 110[[1.1.margin_gold_diff]].", ROWS)
    assert result.problems == ["110 cites 1.1.margin_gold_diff, which is 112"]


def test_an_uncited_number_fails_except_list_numbering_and_1_in_20():
    result = check("1. About 1 in 20 rows look clear by chance.\n2. You played 92 games.", ROWS)
    assert result.problems == ["92 has no citation"]


def test_a_citation_to_nothing_fails():
    assert check("92[[1.7.games]] games.", ROWS).problems == [
        "92 cites 1.7.games, which isn't a field of any tool result"
    ]
    assert check("92[[1.1.wins]] games.", ROWS).problems == [
        "92 cites 1.1.wins, which isn't a field of any tool result"
    ]


def test_notes_descriptions_and_game_times_can_be_cited():
    notes = labelled("compare_to_benchmark", {"notes": ["A benchmark needs 30 games and 10 players."]}, call=2)
    reply = "It needs 30[[2.0.notes]] games, and early means before 15:00[[deaths_by_phase]]."
    assert check(reply, notes).problems == []
    assert check("Before 14:30[[deaths_by_phase]].", notes).problems == ["14:30 isn't a whole minute"]


def test_digits_in_the_players_riot_id_need_no_citation():
    # A Riot ID's tag can be all digits; anywhere else, 1234 would need a citation.
    assert check("Ana#1234 played 92[[1.1.games]] games.", ROWS, exempt=("Ana#1234",)).problems == []
    assert check("Tag 1234 played 92[[1.1.games]] games.", ROWS, exempt=("Ana#1234",)).problems == [
        "1234 has no citation"
    ]


# Replays of the recorded errors, with the citations a model would plausibly write


DRAFT = labelled(
    "draft_board",
    {
        "pool": [
            {"champion": "DrMundo", "games": 17, "win_rate_pct": 52.9, "margin_win_rate_pct": 24.5},
            {"champion": "Zaahen", "games": 15, "win_rate_pct": 33.3, "margin_win_rate_pct": 24.7},
            {"champion": "Viego", "games": 8, "win_rate_pct": 25.0, "margin_win_rate_pct": 32.1},
        ]
    },
)


def test_the_25_rounding_is_caught_when_it_cites_the_margin_it_rounded():
    """v4's draft reply: "margins of around ±25 points", from 24.5 and 24.7."""
    mundo = ref_of(DRAFT, champion="DrMundo")
    result = check(f"Their win rates have margins of around ±25[[{mundo}.margin_win_rate_pct]] points.", DRAFT)
    assert result.problems == [f"25 cites {mundo}.margin_win_rate_pct, which is 24.5"]


def test_the_25_passes_only_by_citing_viegos_win_rate_and_the_hover_says_so():
    """The limit: 25.0 is a real field, but Viego's win rate, not a margin."""
    viego = ref_of(DRAFT, champion="Viego")
    result = check(f"Margins of around ±25[[{viego}.win_rate_pct]] points.", DRAFT)
    assert result.problems == []
    assert result.citations[0].label == "draft_board: pool, champion Viego → win_rate_pct"


MUNDO = labelled(
    "compare_to_benchmark",
    {
        "rows": [
            {"metric": "lane_diff", "minute": 10, "result": "win", "value": "avg_gold_diff", "my_sample": 9},
            {"metric": "lane_diff", "minute": 10, "result": "loss", "value": "avg_gold_diff", "my_sample": 8},
        ]
    },
)


def test_mundos_8_is_caught_when_it_cites_the_wins():
    win = ref_of(MUNDO, result="win")
    result = check(f"Those splits have 8[[{win}.my_sample]] or fewer games each.", MUNDO)
    assert result.problems == [f"8 cites {win}.my_sample, which is 9"]


def test_mundos_8_passes_when_it_cites_the_losses_because_the_error_is_the_word_each():
    """The limit: 8 is right for the losses; "each" wrongly covers the wins' 9."""
    loss = ref_of(MUNDO, result="loss")
    result = check(f"Those splits have 8[[{loss}.my_sample]] or fewer games each.", MUNDO)
    assert result.problems == []
    assert result.citations[0].label == "compare_to_benchmark: metric lane_diff, value avg_gold_diff, minute 10, result loss → my_sample"


# The coach loop with a model that cites


async def win_rate_game(sessions):
    from test_analytics import add_game

    async with sessions() as session:
        for n in range(3):
            await add_game(session, f"EUW1_{n}", champion="Viego", win=n < 2)


def ref_in(model, **match):
    """The ref the model was sent for the object with these fields."""
    content = model.sent[1][-1]["content"][0]["content"]
    return ref_of(("win_rates", content), **match)


async def test_results_are_labelled_and_a_correct_reply_is_shown_without_markers(sessions):
    from fakes import CitingModel, calls, says

    from agent.coach import ask_coach
    from agent.tools import ToolContext

    await win_rate_game(sessions)
    model = CitingModel(calls(("win_rates", {"champion": None})), says("placeholder"))
    context = ToolContext(sessions, None, ("me",))

    async def reply_with_refs():
        # The second reply is written after seeing the labelled result.
        row = ref_in(model, dimension="champion", value="Viego")
        return says(f"You won 2[[{row}.wins]] of 3[[{row}.games]] Viego games.")

    original = model.send

    async def send(system, tools, messages, max_tokens=16_000):
        reply = await original(system, tools, messages, max_tokens)
        return await reply_with_refs() if reply.text == "placeholder" else reply

    model.send = send
    answer = await ask_coach(model, context, "How is my Viego?")

    assert "Citations" in model.system
    assert answer.status == "verified"
    assert answer.text == "You won 2 of 3 Viego games."
    assert answer.linked_text == "You won [2](cite:0) of [3](cite:1) Viego games."
    assert answer.citations[0]["label"].startswith("win_rates: dimension champion, value Viego")


async def test_a_wrong_citation_gets_one_retry_naming_the_problem(sessions):
    from fakes import CitingModel, calls, says

    from agent.coach import ask_coach
    from agent.tools import ToolContext

    await win_rate_game(sessions)
    # Both rows, Viego and the jungle role, cover all 3 games, so 1.1.games is 3
    # whichever comes first.
    model = CitingModel(
        calls(("win_rates", {"champion": None})),
        says("You played 4[[1.1.games]] games."),
        says("You played 3[[1.1.games]] games."),
    )
    answer = await ask_coach(model, ToolContext(sessions, None, ("me",)), "How many games?")

    assert answer.status == "verified"
    assert answer.caught_numbers == ["4 cites 1.1.games, which is 3"]
    assert "4 cites 1.1.games, which is 3" in model.sent[2][-1]["content"]


async def test_an_uncited_number_twice_is_shown_with_a_warning(sessions):
    from fakes import CitingModel, calls, says

    from agent.coach import ask_coach
    from agent.tools import ToolContext

    await win_rate_game(sessions)
    model = CitingModel(calls(("win_rates", {"champion": None})), says("You played 3 games."), says("Still 3 games."))
    answer = await ask_coach(model, ToolContext(sessions, None, ("me",)), "How many games?")

    assert answer.status == "unverified"
    assert answer.text.startswith("Warning: the check couldn't match these numbers")
    assert "3 has no citation" in answer.text


async def test_a_model_that_doesnt_cite_keeps_the_plain_check(sessions):
    from fakes import FakeModel, calls, says

    from agent.coach import ask_coach
    from agent.tools import ToolContext

    await win_rate_game(sessions)
    model = FakeModel(calls(("win_rates", {"champion": None})), says("You played 3 games."))
    answer = await ask_coach(model, ToolContext(sessions, None, ("me",)), "How many games?")

    assert (answer.status, answer.text, answer.citations) == ("verified", "You played 3 games.", [])
    assert "Citations" not in model.system
    assert '"ref"' not in model.sent[1][-1]["content"][0]["content"]


# Minute labels: uncited, but checked against the minutes the results define


LANE = labelled("lane_diff", {"rows": [{"minute": 10, "games": 92}, {"minute": 15, "games": 91}, {"minute": 20, "games": 85}]})


def test_minute_labels_need_no_citation_when_the_results_define_them():
    reply = (
        "At minute 15: you're behind. Between the 10-minute and 15-minute marks the gap "
        "grows, at 10, 15 and 20 minutes alike, and early deaths are before 15:00."
    )
    assert check(reply, LANE).problems == []


def test_a_minute_label_the_results_dont_define_fails():
    assert check("At minute 12 you fall behind.", LANE).problems == ["12 isn't a minute any tool result defines"]
    assert check("By 17 minutes it's over.", LANE).problems == ["17 isn't a minute any tool result defines"]


def test_a_number_beside_a_minute_label_still_needs_its_citation():
    """The label is free; the measured number in the same sentence isn't."""
    assert check("At minute 15 you have 91 games.", LANE).problems == ["91 has no citation"]


def test_minute_0_is_the_start_of_the_game():
    assert check("In the first 0-10 minutes you fall behind.", LANE).problems == []


def test_stretch_boundaries_are_minutes_too():
    stretch = labelled("farm_by_stretch", {"rows": [{"stretch": "10-15", "games": 90}]})
    assert check("Between minutes 10 and 15 you lose ground.", stretch).problems == []


# Fixes after the 16-case run


def test_a_game_time_that_ends_a_bold_heading_is_still_a_time():
    assert check("**The window from 15:00 to 20:00:** take your camps.", LANE).problems == []


def test_a_decimal_after_a_minute_list_is_a_number_not_a_minute():
    result = check("13.2[[1.1.games]] behind at minute 15 and 21.8 behind at minute 20.", LANE)
    assert result.problems == ["13.2 cites 1.1.games, which is 92", "21.8 has no citation"]


def test_a_nested_side_is_labelled_with_its_row_and_side():
    """A wins_and_losses row nests its sides: a citation to one names the row."""
    result = labelled(
        "wins_and_losses",
        {"rows": [{"metric": "objective_share", "objective": "BARON_NASHOR", "value": "team_share_pct",
                   "wins": {"value": 83.0, "sample": 47}, "losses": {"value": 16.7, "sample": 54}}]},
        call=2,
    )
    losses = json.loads(result[1])["rows"][0]["losses"]["ref"]
    cited = check(f"54[[{losses}.sample]] Barons in losses.", result).citations[0]
    assert cited.label == (
        "wins_and_losses: metric objective_share, value team_share_pct, objective BARON_NASHOR, losses → sample"
    )
