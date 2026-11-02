import { describe, expect, it } from "vitest";

import type { CompareRow } from "./api";
import { barLengths } from "./bars";

const row = (mine: number, theirs: number, myMargin: number, theirMargin: number): CompareRow => ({
  metric: "m",
  value: "win_rate_pct",
  theme: "results",
  higher_is_better: true,
  sample_unit: "games",
  my_value: mine,
  my_sample: 30,
  my_low_sample: false,
  my_margin: myMargin,
  benchmark_value: theirs,
  benchmark_sample: 500,
  benchmark_margin: theirMargin,
  difference: mine - theirs,
  difference_margin: myMargin + theirMargin,
  difference_pct: null,
  clear_gap: false,
  strong_gap: false,
  status: "ok",
});

describe("bar lengths", () => {
  it("draws your lower win rate shorter, however wide your margin", () => {
    const bars = barLengths(row(46.7, 48.0, 18.2, 4.4), 300)!;
    expect(bars.mine).toBeLessThan(bars.theirs);
  });

  it("ends each bar exactly at its value", () => {
    const bars = barLengths(row(46.7, 48.0, 18.2, 4.4), 300)!;
    expect(bars.theirs).toBe(300);
    expect(bars.mine).toBeCloseTo((46.7 / 48.0) * 300);
  });

  it("never draws a smaller value as a longer bar", () => {
    // A fixed pseudo-random sweep: values and margins in every combination of sizes.
    let seed = 7;
    const next = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
    for (let i = 0; i < 2000; i++) {
      const mine = next() * 100;
      const theirs = next() * 100;
      const bars = barLengths(row(mine, theirs, next() * 50, next() * 50), 300)!;
      if (mine < theirs) expect(bars.mine).toBeLessThanOrEqual(bars.theirs);
      if (theirs < mine) expect(bars.theirs).toBeLessThanOrEqual(bars.mine);
    }
  });

  it("leaves negative gaps to text", () => {
    expect(barLengths(row(-4.9, 0, 1, 1), 300)).toBeNull();
  });
});
