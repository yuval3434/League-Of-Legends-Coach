import { describe, expect, it } from "vitest";

import type { PoolEntry } from "./api";
import { add, cantAdd, coachQuestion, EMPTY, remove, winRateCell } from "./draft";

const entry = (over: Partial<PoolEntry> = {}): PoolEntry => ({
  champion: "DrMundo",
  games: 17,
  wins: 9,
  win_rate_pct: 52.9,
  margin_win_rate_pct: 24.5,
  ...over,
});

describe("the board", () => {
  it("keeps each side within champion select's limits", () => {
    let board = EMPTY;
    for (const c of ["Jinx", "Ahri", "Lulu", "Garen"]) board = add(board, "allies", c);
    expect(cantAdd(board, "allies", "Sona")).toBe("4 at most");
    expect(add(board, "allies", "Sona")).toBe(board);
  });

  it("puts a champion on the board only once, picks and bans alike", () => {
    const board = add(EMPTY, "bans", "Viego");
    expect(cantAdd(board, "enemies", "Viego")).toBe("Already on the board");
    expect(remove(board, "bans", "Viego")).toEqual(EMPTY);
  });
});

describe("win rates", () => {
  it("gives the rate with its margin from 10 games", () => {
    expect(winRateCell(entry())).toEqual({ main: "52.9%", detail: "give or take 24.5 · won 9 of 17" });
  });

  it("says too early to tell under 10 games, or with no spread", () => {
    expect(winRateCell(entry({ games: 5, wins: 4, low_sample: true })).main).toBe("Too early to tell");
    expect(winRateCell(entry({ games: 3, wins: 3, margin_win_rate_pct: 0, low_sample: true }))).toEqual({
      main: "Too early to tell",
      detail: "won 3 of 3",
    });
  });
});

describe("the coach question", () => {
  it("lists the board and asks to be shown, not told what to pick", () => {
    const name = (id: string) => ({ LeeSin: "Lee Sin" })[id] ?? id;
    const q = coachQuestion({ allies: ["Jinx", "Ahri", "Lulu"], enemies: ["LeeSin"], bans: ["Viego"] }, name);
    expect(q).toBe(
      "Champion select: my team has Jinx, Ahri and Lulu, the enemy has Lee Sin, Viego is banned. " +
        "What does my team lack, and which of my champions fill it?",
    );
    expect(q).not.toMatch(/should I pick|best/i);
  });
});
