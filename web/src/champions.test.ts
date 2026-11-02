import { describe, expect, it } from "vitest";

import type { ChampionRow } from "./api";
import { nextSort, rangeWords, sortChampions } from "./champions";
import { parseRoute, askCoach } from "./router";

const row = (champion: string, games: number, win_rate_pct: number): ChampionRow => ({
  champion, games, win_rate_pct, wins: 0, kills: 0, deaths: 0, assists: 0, kda: 1, cs_per_min: 5,
  margin_win_rate_pct: null, win_rate_low_pct: null, win_rate_high_pct: null,
});
const rows = [row("Viego", 8, 25), row("DrMundo", 18, 50), row("Nunu", 5, 80), row("Zaahen", 15, 33.3)];
const ids = (r: ChampionRow[]) => r.map((x) => x.champion);

describe("champion sorting", () => {
  it("sorts by win rate, highest first", () => {
    expect(ids(sortChampions(rows, { key: "win_rate_pct", descending: true }))).toEqual(["Nunu", "DrMundo", "Zaahen", "Viego"]);
  });

  it("sorts names by their display name", () => {
    const name = (id: string) => (id === "DrMundo" ? "Dr. Mundo" : id);
    expect(ids(sortChampions(rows, { key: "champion", descending: false }, name))).toEqual(["DrMundo", "Nunu", "Viego", "Zaahen"]);
  });

  it("breaks ties by games played", () => {
    const tied = [row("A", 3, 50), row("B", 9, 50)];
    expect(ids(sortChampions(tied, { key: "win_rate_pct", descending: true }))).toEqual(["B", "A"]);
  });

  it("flips direction on a second click, and starts numbers high and names low", () => {
    expect(nextSort({ key: "games", descending: true }, "games")).toEqual({ key: "games", descending: false });
    expect(nextSort({ key: "games", descending: true }, "kda")).toEqual({ key: "kda", descending: true });
    expect(nextSort({ key: "games", descending: true }, "champion")).toEqual({ key: "champion", descending: false });
  });
});

describe("win rate range", () => {
  it("gives the server's range in plain words", () => {
    const mundo = { ...row("DrMundo", 17, 52.9), margin_win_rate_pct: 24.5, win_rate_low_pct: 28, win_rate_high_pct: 77 };
    expect(rangeWords(mundo)).toBe("could be anywhere from 28% to 77% on 17 games");
  });

  it("gives no range under 10 games", () => {
    const viego = { ...row("Viego", 8, 25), low_sample: true, margin_win_rate_pct: 32.1, win_rate_low_pct: 0, win_rate_high_pct: 57 };
    expect(rangeWords(viego)).toBe("too early to tell on 8 games");
  });

  it("doesn't call a perfect record certain", () => {
    const perfect = { ...row("Amumu", 10, 100), wins: 10, margin_win_rate_pct: 0, win_rate_low_pct: 100, win_rate_high_pct: 100 };
    expect(rangeWords(perfect)).toBe("10 games, all won: too few to give a range");
  });
});

describe("routes", () => {
  it("carries a question to the Coach page", () => {
    const route = parseRoute(askCoach("How am I doing on Dr. Mundo?"));
    expect(route.page).toBe("coach");
    expect(route.params.get("q")).toBe("How am I doing on Dr. Mundo?");
  });

  it("falls back to the Overview", () => {
    expect(parseRoute("#/nowhere").page).toBe("overview");
  });
});
