import { describe, expect, it } from "vitest";

import type { Theme } from "./api";
import { headline } from "./headline";
import { decimalsOf, fmt, gapWords, signed } from "./metrics";

const row = (value: string) => ({ metric: "m", value });
const finding = (theme: string, direction: "behind" | "ahead", values: string[]): Theme => ({
  theme,
  status: "finding",
  findings: [{ direction, basis: "agreeing_metrics", rows: values.map(row) }],
});

describe("headline", () => {
  it("names each finding you're behind on", () => {
    const themes = [
      finding("economy", "behind", ["avg_cs", "avg_gold"]),
      finding("vision", "behind", ["avg_placed_per_min"]),
    ];
    expect(headline(themes, "Silver junglers")).toBe(
      "You're behind Silver junglers on farm, and on wards placed.",
    );
  });

  it("says ahead and behind in one sentence", () => {
    const themes = [
      finding("economy", "behind", ["avg_cs"]),
      finding("deaths", "ahead", ["avg_deaths"]),
    ];
    expect(headline(themes, "Silver junglers")).toBe(
      "You're behind Silver junglers on farm, and ahead on deaths.",
    );
  });

  it("claims nothing when there are no findings", () => {
    const themes: Theme[] = [{ theme: "economy", status: "worth_watching" }];
    expect(headline(themes, "Silver junglers")).toBe(
      "Nothing in your games stands out from Silver junglers yet.",
    );
  });
});

describe("formatting", () => {
  it("keeps a value's own precision", () => {
    expect(decimalsOf(5.45)).toBe(2);
    expect(fmt(3584)).toBe("3,584");
    expect(fmt(0.119)).toBe("0.119");
  });

  it("uses a real minus sign and marks gains with a plus", () => {
    expect(signed(-158)).toBe("−158");
    expect(signed(0.042)).toBe("+0.042");
  });

  it("shows a dash for a missing value", () => {
    expect(fmt(null)).toBe("—");
  });
});

describe("gap in words", () => {
  const base = {
    metric: "m",
    theme: "economy",
    higher_is_better: true,
    sample_unit: "games",
    my_sample: 30,
    my_low_sample: false,
    my_margin: 0.1,
    benchmark_sample: 500,
    benchmark_margin: 0.1,
    difference_margin: 0.1,
    clear_gap: true,
    strong_gap: false,
    status: "ok" as const,
  };

  it("uses the server's percentage for plain measures", () => {
    const row = { ...base, value: "avg_cs_per_min", my_value: 5.45, benchmark_value: 6.27, difference: -0.82, difference_pct: -13 };
    expect(gapWords(row, "Silver")).toBe("13% behind Silver");
  });

  it("says points for rates and units for gaps against an opponent", () => {
    const rate = { ...base, value: "win_rate_pct", my_value: 46.7, benchmark_value: 48.0, difference: -1.3, difference_pct: null };
    const lane = { ...base, value: "avg_cs_diff", my_value: -4.9, benchmark_value: 0.0, difference: -4.9, difference_pct: null };
    expect(gapWords(rate, "Silver")).toBe("1.3 points behind Silver");
    expect(gapWords(lane, "Silver")).toBe("4.9 CS behind Silver");
  });

  it("counts more deaths as behind", () => {
    const deaths = { ...base, value: "avg_deaths", higher_is_better: false, my_value: 2.5, benchmark_value: 2.0, difference: 0.5, difference_pct: 25 };
    expect(gapWords(deaths, "Silver")).toBe("25% behind Silver");
  });

  it("says within 1% when the percentage rounds to zero", () => {
    const row = { ...base, value: "avg_deaths", higher_is_better: false, my_value: 2.23, benchmark_value: 2.22, difference: 0.01, difference_pct: 0 };
    expect(gapWords(row, "Silver")).toBe("within 1% of Silver");
  });
});
