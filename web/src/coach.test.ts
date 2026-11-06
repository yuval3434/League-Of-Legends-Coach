import { describe, expect, it } from "vitest";

import type { CoachTool } from "./api";
import { citationFor, costWords, restsOnFewGames, sampleWords, toolLabel } from "./coach";

const tool = (name: string, args: Record<string, unknown>, extra: Partial<CoachTool> = {}): CoachTool => ({
  name,
  arguments: args,
  ...extra,
});

describe("tool labels", () => {
  it("names the rank, theme and champion a comparison was asked for", () => {
    const t = tool("compare_to_benchmark", { cohort: "silver", theme: "economy", champion: "DrMundo" });
    expect(toolLabel(t, (id) => (id === "DrMundo" ? "Dr. Mundo" : id))).toBe("Comparison with Silver, farm, on Dr. Mundo");
  });

  it("leaves out arguments that weren't set", () => {
    expect(toolLabel(tool("win_rates", { champion: null }))).toBe("Win rates");
    expect(toolLabel(tool("champion_stats", { role: "JUNGLE" }))).toBe("Champion stats, jungle");
  });
});

describe("sample words", () => {
  it("gives your range of games and the benchmark's", () => {
    const t = tool("compare_to_benchmark", {}, { your_games: { min: 26, max: 30 }, benchmark_games: 500, status: "ok" });
    expect(sampleWords(t)).toBe("Your 26–30 games · 500 benchmark games");
  });

  it("flags rows on too few games", () => {
    const t = tool("win_rates", {}, { your_games: { min: 1, max: 18 }, low_sample_rows: 20 });
    expect(sampleWords(t)).toBe("Your 1–18 games · 20 under 10 games");
    expect(restsOnFewGames(t)).toBe(true);
  });

  it("says when the tool refused", () => {
    expect(sampleWords(tool("lane_diff", {}, { error: true }))).toBe("The tool refused the request");
  });
});

describe("cost", () => {
  it("shows the cost to a tenth of a cent, and marks an upper bound", () => {
    expect(costWords({ cost_usd: 0.08027, cost_is_upper_bound: false })).toBe("$0.080");
    expect(costWords({ cost_usd: 0.12, cost_is_upper_bound: true })).toBe("At most $0.120");
    expect(costWords({ cost_usd: null, cost_is_upper_bound: false })).toBe("Cost unknown");
  });
});

describe("citations", () => {
  const citations = [{ number: "184", target: "2.14.avg_gold_diff", label: "lane_diff: minute 10 → avg_gold_diff" }];

  it("finds the source of a cite link", () => {
    expect(citationFor("cite:0", citations)).toBe("lane_diff: minute 10 → avg_gold_diff = 184");
  });

  it("ignores other links and unknown citations", () => {
    expect(citationFor("https://example.com", citations)).toBeNull();
    expect(citationFor("cite:7", citations)).toBeNull();
    expect(citationFor(undefined, citations)).toBeNull();
  });
});
