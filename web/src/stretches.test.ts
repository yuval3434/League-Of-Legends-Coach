import { describe, expect, it } from "vitest";

import type { CohortStretch, OpponentStretch, StretchCohort } from "./api";
import { cohortCell, opponentCell } from "./stretches";

function jungler(over: Partial<OpponentStretch> = {}): OpponentStretch {
  return {
    stretch: "10-15",
    start_minute: 10,
    end_minute: 15,
    games: 84,
    low_sample: false,
    avg_gold_diff: -234,
    margin_gold_diff: 160,
    avg_cs_diff: 1.5,
    margin_cs_diff: 2.8,
    clear_gold_diff: true,
    clear_cs_diff: false,
    ...over,
  };
}

function cohort(row: Partial<CohortStretch> = {}, over: Partial<StretchCohort> = {}): StretchCohort {
  return {
    cohort: "silver",
    tier: "SILVER",
    audience: "peers",
    status: "ok",
    benchmark_games: 500,
    benchmark_players: 100,
    rows: [
      {
        metric: "farm_gained_by_stretch",
        stretch: "10-15",
        value: "avg_gold_gained",
        higher_is_better: true,
        sample_unit: "games",
        my_value: 1868,
        my_sample: 84,
        my_low_sample: false,
        my_margin: 87,
        benchmark_value: 2093,
        benchmark_sample: 497,
        benchmark_margin: 47,
        difference: -225,
        difference_pct: -11,
        difference_margin: 99,
        clear_gap: true,
        strong_gap: true,
        status: "ok",
        ...row,
      },
    ],
    ...over,
  };
}

describe("against the enemy jungler", () => {
  it("says what was lost, with its margin and games", () => {
    expect(opponentCell(jungler(), "gold")).toEqual({
      main: "Lost 234 gold",
      detail: "give or take 160 · 84 games",
      tone: "clear",
    });
  });

  it("says when a gain could be chance", () => {
    expect(opponentCell(jungler(), "cs")).toEqual({
      main: "Gained 1.5 CS",
      detail: "give or take 2.8 · 84 games · could be chance",
      tone: "unclear",
    });
  });

  it("gives no amount under 10 games", () => {
    expect(opponentCell(jungler({ games: 6, low_sample: true }), "gold")).toEqual({
      main: "Too few games",
      detail: "6 games",
      tone: "low",
    });
  });
});

describe("against a cohort", () => {
  it("words the gap the API gives, with both samples", () => {
    expect(cohortCell(cohort(), "10-15", "gold", "Silver")).toEqual({
      main: "225 less gold than Silver",
      detail: "give or take 99 · 84 games against 497",
      tone: "clear",
    });
  });

  it("shows the margin as precisely as the values", () => {
    expect(cohortCell(cohort({ difference_margin: 129.449 }), "10-15", "gold", "Silver").detail).toBe(
      "give or take 129 · 84 games against 497",
    );
    const cs = cohort({ value: "avg_cs_gained", my_value: 29.4, benchmark_value: 32.5, difference: -3.1, difference_margin: 3.008 });
    expect(cohortCell(cs, "10-15", "cs", "Silver")).toMatchObject({
      main: "3.1 less CS than Silver",
      detail: "give or take 3.0 · 84 games against 497",
    });
  });

  it("says no benchmark rather than anything else", () => {
    const none = cohort({}, { status: "no_benchmark", rows: [] });
    expect(cohortCell(none, "10-15", "gold", "Silver").main).toBe("No benchmark");
    expect(cohortCell(cohort({ status: "no_benchmark" }), "10-15", "gold", "Silver").main).toBe("No benchmark");
  });

  it("gives no amount under 10 of the player's games", () => {
    expect(cohortCell(cohort({ my_sample: 4, my_low_sample: true }), "10-15", "gold", "Silver").main).toBe(
      "Too few games",
    );
  });

  it("says a gap inside the margin could be chance", () => {
    const cell = cohortCell(cohort({ difference: 30, clear_gap: false }), "10-15", "gold", "Silver");
    expect(cell.main).toBe("30 more gold than Silver");
    expect(cell.detail).toContain("could be chance");
  });
});
