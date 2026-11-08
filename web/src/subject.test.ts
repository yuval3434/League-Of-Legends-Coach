import { describe, expect, it } from "vitest";

import type { ChampionRow, CompareRow, Comparison, Theme } from "./api";
import { rangeWords } from "./champions";
import { type Compared, compareHeadline } from "./compare";
import { headline } from "./headline";
import { href, parseRoute } from "./router";
import { subjectOf, verb, YOU } from "./subject";

/** The Compare page's two jungle cohorts: Silver as peers, Emerald as a target. */
function jungleCohorts(peers: Comparison, target: Comparison): Compared[] {
  return [
    { slot: "peers", short: "Silver", group: "Silver junglers", comparison: peers },
    { slot: "target", short: "Emerald", group: "Emerald junglers", comparison: target },
  ];
}

const ANA = subjectOf({ is_owner: false, game_name: "Ana" });

describe("subject", () => {
  it("is you for the owner and a name for anyone else", () => {
    expect(subjectOf({ is_owner: true, game_name: "Me" })).toEqual(YOU);
    expect(ANA).toEqual({ you: false, name: "Ana" });
    expect(verb(YOU, "farm")).toBe("farm");
    expect(verb(ANA, "farm")).toBe("farms");
    expect(verb(ANA, "have")).toBe("has");
  });
});

describe("another player's wording", () => {
  it("names them in the headline", () => {
    const themes: Theme[] = [
      { theme: "economy", status: "finding", findings: [{ direction: "behind", basis: "agreeing_metrics", rows: [] }] },
    ];
    expect(headline(themes, "Silver junglers", ANA)).toBe("Ana is behind Silver junglers on farm.");
    expect(headline([], "Silver junglers", ANA)).toBe("Nothing in Ana's games stands out from Silver junglers yet.");
  });

  it("names them in the win-rate range", () => {
    const row = { champion: "Viego", games: 18, wins: 9, win_rate_pct: 50, margin_win_rate_pct: 23.8, win_rate_low_pct: 26, win_rate_high_pct: 74 } as ChampionRow;
    expect(rangeWords(row, ANA)).toBe(
      "Ana won 9 of 18. That's too few games to tell how good Ana really is on this champion — Ana's true win rate could be anywhere from about 26% to 74%.",
    );
  });
});

describe("compare headline with one cohort", () => {
  const cs = (pct: number): CompareRow => ({
    metric: "gold_cs_at_minute", theme: "economy", value: "avg_cs", minute: 20,
    higher_is_better: true, sample_unit: "games",
    my_value: 112.4, my_sample: 26, my_low_sample: false, my_margin: 6,
    benchmark_value: 142.6, benchmark_sample: 459, benchmark_margin: 2,
    difference: -30.2, difference_pct: pct, difference_margin: 6, clear_gap: true, strong_gap: false, status: "ok",
  });
  const ok = (cohort: string, rows: CompareRow[]): Comparison => ({
    cohort, tier: cohort.toUpperCase(), role: "JUNGLE", status: "ok", benchmark_games: 500, benchmark_players: 440,
    benchmark_patches: ["16.21"], rows, themes: [], notes: [],
  });
  const none = (cohort: string): Comparison => ({ ...ok(cohort, []), status: "no_benchmark" });

  it("names only the cohort that fits", () => {
    expect(compareHeadline(jungleCohorts(none("silver"), ok("emerald", [cs(-21)])), ANA)).toBe(
      "At 20 minutes Ana has 21% less CS than Emerald junglers",
    );
  });

  it("says when no cohort fits", () => {
    expect(compareHeadline(jungleCohorts(none("silver"), none("emerald")), ANA)).toBe("No benchmark fits Ana yet");
  });
});

describe("the selected player in links", () => {
  it("carries the player to every page, and drops it for the owner", () => {
    const here = "#/champions?player=abc";
    expect(href("compare", {}, here)).toBe("#/compare?player=abc");
    expect(parseRoute(href("coach", { q: "Hi?" }, here)).params.get("player")).toBe("abc");
    expect(href("overview", { player: "" }, here)).toBe("#/overview");
    expect(href("overview", {}, "#/overview")).toBe("#/overview");
  });
});
