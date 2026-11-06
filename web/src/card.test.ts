import { describe, expect, it } from "vitest";

import type { CardBenchmark } from "./api";
import { benchmarkLines, estimateWords, sideCell, upTo } from "./card";

describe("card cells", () => {
  it("gives the value, its margin and games", () => {
    expect(sideCell("cs_per_min", { value: 5.92, margin: 0.37, games: 17, low_sample: false })).toEqual({
      main: "5.92",
      detail: "give or take 0.37 · 17 games",
      low: false,
    });
  });

  it("greys a value under 10 games and says too early to tell", () => {
    expect(sideCell("gold_at_15", { value: 5960, margin: 501, games: 5, low_sample: true })).toEqual({
      main: "5,960",
      detail: "too early to tell · 5 games",
      low: true,
    });
    expect(sideCell("kill_participation", null).main).toBe("—");
  });
});

const base = { cohort: "silver", tier: "SILVER", benchmark_games: 34, benchmark_players: 31 } as const;

describe("the champion benchmark", () => {
  it("gives win rate, CS per minute and the sample", () => {
    const b: CardBenchmark = {
      ...base,
      status: "ok",
      benchmark_patches: ["16.19", "16.20", "16.21"],
      cs_per_min: { value: 5.81, margin: 0.41 },
      win_rate: { value: 58.8, margin: 16.8 },
    };
    expect(benchmarkLines(b, "Silver", "Nunu & Willump")).toEqual({
      main: "Silver junglers on Nunu & Willump",
      details: [
        "Win rate 58.8%, give or take 16.8.",
        "CS per minute 5.81, give or take 0.41.",
        "34 Silver games on Nunu & Willump from 31 players, patches 16.19 to 16.21.",
      ],
    });
  });

  it("doesn't compare an Emerald win rate", () => {
    const b: CardBenchmark = {
      ...base,
      cohort: "emerald",
      status: "ok",
      benchmark_patches: ["16.21"],
      cs_per_min: { value: 6.39, margin: 0.27 },
      win_rate: "not_comparable",
    };
    expect(benchmarkLines(b, "Emerald", "Nunu").details[0]).toBe(
      "Win rate not compared: Emerald junglers face Emerald opponents.",
    );
  });

  it("says no benchmark, with the sample and the rule", () => {
    const b: CardBenchmark = {
      ...base,
      benchmark_games: 19,
      benchmark_players: 16,
      status: "no_benchmark",
      note: "A benchmark on one champion needs 30 games from 10 players.",
    };
    expect(benchmarkLines(b, "Silver", "Dr. Mundo")).toEqual({
      main: "No benchmark",
      details: ["19 Silver games on Dr. Mundo from 16 players.", "A benchmark on one champion needs 30 games from 10 players."],
    });
  });
});

describe("the options ceiling", () => {
  it("rounds the ceiling up to the cent", () => {
    expect(upTo(0.1851)).toBe("$0.19");
    expect(upTo(0.004)).toBe("under $0.01");
  });

  it("states what was counted and what's capped", () => {
    const words = estimateWords(
      { model: "claude-sonnet-5-5", champions: [], input_tokens: 10000, max_output_tokens: 6000, max_cost_usd: 0.1855, one_call_max_usd: 0.085 },
      "Sonnet 5.5",
    );
    expect(words.main).toBe("Up to $0.19 on Sonnet 5.5");
    expect(words.detail).toContain("10,000 input tokens, counted now");
    expect(words.detail).toContain("without it, up to $0.09");
  });

  it("says the local model is free", () => {
    const words = estimateWords(
      { model: "local", champions: [], input_tokens: null, max_output_tokens: null, max_cost_usd: 0 },
      "Local",
    );
    expect(words.main).toBe("Free on Local");
  });
});
