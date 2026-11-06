import { describe, expect, it } from "vitest";

import type { ChampionRow } from "./api";
import { nextSort, rangeWords, roleSplit, sortChampions } from "./champions";
import { parseRoute, askCoach } from "./router";

const row = (champion: string, games: number, win_rate_pct: number): ChampionRow => ({
  champion, games, win_rate_pct, wins: 0, kills: 0, deaths: 0, assists: 0, kda: 1, cs_per_min: 5,
  margin_win_rate_pct: null, win_rate_low_pct: null, win_rate_high_pct: null, games_by_role: {},
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
    const mundo = { ...row("DrMundo", 18, 50), wins: 9, margin_win_rate_pct: 23.8, win_rate_low_pct: 26, win_rate_high_pct: 74 };
    expect(rangeWords(mundo)).toBe(
      "You won 9 of 18. That's too few games to tell how good you really are on this champion — your true win rate could be anywhere from about 26% to 74%.",
    );
  });

  it("gives no range under 10 games", () => {
    const viego = { ...row("Viego", 8, 25), wins: 2, low_sample: true, margin_win_rate_pct: 32.1, win_rate_low_pct: 0, win_rate_high_pct: 57 };
    expect(rangeWords(viego)).toBe("You won 2 of 8. That's too few games to tell how good you really are on this champion.");
  });

  it("doesn't call a perfect record certain", () => {
    const perfect = { ...row("Amumu", 10, 100), wins: 10, margin_win_rate_pct: 0, win_rate_low_pct: 100, win_rate_high_pct: 100 };
    expect(rangeWords(perfect)).toBe("You won 10 of 10. That's too few games to tell how good you really are on this champion.");
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

describe("the games split by role", () => {
  it("lists the most played role first", () => {
    expect(roleSplit({ games: 18, games_by_role: { TOP: 1, JUNGLE: 17 } })).toBe("18 games: 17 jungle, 1 top");
  });

  it("names games Riot gave no role", () => {
    expect(roleSplit({ games: 3, games_by_role: { MIDDLE: 2, "": 1 } })).toBe("3 games: 2 mid, 1 with no role");
  });
});
