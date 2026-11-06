import { describe, expect, it } from "vitest";

import type { CompareRow, Comparison } from "./api";
import { compareHeadline, minutePoints } from "./compare";

const cs = (minute: number, mine: number, theirs: number, pct: number): CompareRow => ({
  metric: "gold_cs_at_minute", theme: "economy", value: "avg_cs", minute,
  higher_is_better: true, sample_unit: "games",
  my_value: mine, my_sample: 30, my_low_sample: false, my_margin: 3,
  benchmark_value: theirs, benchmark_sample: 500, benchmark_margin: 1,
  difference: mine - theirs, difference_pct: pct, difference_margin: 4,
  clear_gap: true, strong_gap: false, status: "ok",
});
const comparison = (cohort: string, rows: CompareRow[]): Comparison => ({
  cohort, tier: cohort.toUpperCase(), role: "JUNGLE", status: "ok", benchmark_games: 500, benchmark_players: 450,
  benchmark_patches: ["16.19"], rows, themes: [], notes: [],
});

const silver = comparison("silver", [cs(10, 59.7, 63.7, -6), cs(20, 112.4, 128.9, -13)]);
const emerald = comparison("emerald", [cs(10, 59.7, 69.5, -14), cs(20, 112.4, 142.6, -21)]);

describe("compare headline", () => {
  it("uses the latest minute and the server's percentages", () => {
    expect(compareHeadline(silver, emerald)).toBe(
      "At 20 minutes you have 13% less CS than Silver junglers and 21% less than Emerald",
    );
  });

  it("skips a minute where your sample is too small", () => {
    const thin = comparison("silver", [cs(10, 59.7, 63.7, -6), { ...cs(20, 112.4, 128.9, -13), my_low_sample: true }]);
    expect(compareHeadline(thin, emerald)).toBe(
      "At 10 minutes you have 6% less CS than Silver junglers and 14% less than Emerald",
    );
  });
});

describe("minute points", () => {
  it("puts your line and both benchmarks on each minute, with gaps where a row is missing", () => {
    const points = minutePoints("avg_cs", silver, emerald);
    expect(points.map((p) => [p.minute, p.you, p.silver, p.emerald])).toEqual([
      [10, 59.7, 63.7, 69.5],
      [15, null, null, null],
      [20, 112.4, 128.9, 142.6],
    ]);
  });
});
