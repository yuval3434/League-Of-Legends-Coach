import { describe, expect, it } from "vitest";

import type { OwnRow } from "./api";
import { shownRows, winLossWords } from "./own";

function row(over: Partial<OwnRow> = {}): OwnRow {
  const side = { value: 1, margin: 0.1, sample: 12, low_sample: false };
  return {
    metric: "cs_per_minute",
    theme: "economy",
    higher_is_better: true,
    value: "avg_cs_per_min",
    sample_unit: "games",
    all: side,
    wins: side,
    losses: side,
    difference: 1.4,
    difference_margin: 0.6,
    clear_gap: true,
    ...over,
  };
}

describe("own numbers", () => {
  it("keeps averages and leaves out rates with no margin", () => {
    expect(shownRows([row(), row({ value: "deaths_per_10_min" })]).map((r) => r.value)).toEqual(["avg_cs_per_min"]);
  });

  it("only calls a difference clear with 10+ games on each side", () => {
    expect(winLossWords(row())).toBe("Clearly higher in wins");
    expect(winLossWords(row({ difference: -1 }))).toBe("Clearly lower in wins");
    expect(winLossWords(row({ clear_gap: false }))).toBe("No clear difference");
    expect(winLossWords(row({ wins: { value: 1, margin: null, sample: 9, low_sample: true } }))).toBe("Too early to tell");
    expect(winLossWords(row({ context_only: true }))).toBe("Context, not judged");
  });
});
