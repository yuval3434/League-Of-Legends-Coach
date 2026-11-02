"""The finding rule, on hand-built rows so each case is exact."""

from benchmarks.themes import summarize_themes


def row(value="avg_gold", theme="economy", difference=-100.0, **fields):
    defaults = {
        "metric": "gold_cs_at_minute",
        "theme": theme,
        "value": value,
        "higher_is_better": True,
        "difference": difference,
        "difference_margin": 80.0,
        "clear_gap": True,
        "strong_gap": False,
        "my_low_sample": False,
        "status": "ok",
    }
    return defaults | fields


def theme(rows, name="economy"):
    return next(t for t in summarize_themes(rows) if t["theme"] == name)


def test_one_clear_row_is_only_worth_watching():
    result = theme([row()])
    assert result["status"] == "worth_watching"
    assert result["findings"] == []
    assert len(result["worth_watching"]) == 1


def test_two_metrics_agreeing_make_a_finding():
    result = theme([row("avg_gold"), row("avg_cs")])
    assert result["status"] == "finding"
    assert result["findings"][0]["direction"] == "behind"
    assert result["findings"][0]["basis"] == "agreeing_metrics"


def test_one_metric_at_three_minutes_is_still_one_metric():
    rows = [row("avg_gold", minute=minute) for minute in (10, 15, 20)]
    assert theme(rows)["status"] == "worth_watching"


def test_metrics_pointing_opposite_ways_dont_agree():
    rows = [row("avg_gold", difference=-100.0), row("avg_cs", difference=100.0)]
    assert theme(rows)["status"] == "worth_watching"


def test_deaths_in_different_phases_are_different_metrics():
    rows = [
        row("avg_deaths", "deaths", 1.0, phase="mid", higher_is_better=False),
        row("avg_deaths", "deaths", 1.0, phase="late", higher_is_better=False),
    ]
    result = theme(rows, "deaths")
    assert result["status"] == "finding"
    assert result["findings"][0]["direction"] == "behind"


def test_more_deaths_is_behind_and_fewer_is_ahead():
    fewer = row("avg_deaths", "deaths", -1.0, higher_is_better=False, strong_gap=True)
    assert theme([fewer], "deaths")["findings"][0]["direction"] == "ahead"


def test_a_strong_lone_gap_is_a_finding():
    result = theme([row("avg_placed_per_min", "vision", strong_gap=True)], "vision")
    assert result["status"] == "finding"
    assert result["findings"][0]["basis"] == "strong_gap"


def test_a_strong_gap_leaves_a_weak_one_the_other_way_worth_watching():
    rows = [
        row("avg_placed_per_min", "vision", -0.13, strong_gap=True),
        row("avg_destroyed_per_min", "vision", 0.04),
    ]
    result = theme(rows, "vision")
    assert [f["direction"] for f in result["findings"]] == ["behind"]
    assert [r["value"] for r in result["worth_watching"]] == ["avg_destroyed_per_min"]


def test_a_finding_shows_its_rows_were_clear():
    result = theme([row("avg_gold"), row("avg_cs")])
    assert all(r["clear_gap"] is True for r in result["findings"][0]["rows"])


def test_win_and_loss_rows_dont_count():
    rows = [row("avg_gold_diff", result="win"), row("avg_cs_diff", result="loss")]
    assert theme(rows)["status"] == "no_margin"


def test_rows_on_too_few_games_dont_count():
    rows = [row("avg_gold", my_low_sample=True), row("avg_cs", my_low_sample=True)]
    assert theme(rows)["status"] == "not_enough_data"


def test_a_low_sample_row_cant_be_the_second_metric():
    rows = [row("avg_gold"), row("avg_cs", my_low_sample=True)]
    assert theme(rows)["status"] == "worth_watching"


def test_rows_with_no_margin_give_no_verdict():
    rows = [row("team_share_pct", "objectives", clear_gap=None, strong_gap=None)]
    assert theme(rows, "objectives")["status"] == "no_margin"


def test_a_theme_inside_the_noise_has_nothing_clear():
    assert theme([row(clear_gap=False)])["status"] == "nothing_clear"


def test_a_theme_with_no_benchmark_says_so():
    rows = [row(clear_gap=None, strong_gap=None, status="no_benchmark")]
    assert theme(rows)["status"] == "no_benchmark"


def test_a_theme_with_no_rows_isnt_comparable():
    assert theme([], "objectives")["status"] == "not_comparable"


def test_rows_outside_any_theme_are_ignored():
    themes = summarize_themes([row("win_rate_pct", theme=None)])
    assert all(t["status"] == "not_comparable" for t in themes)
