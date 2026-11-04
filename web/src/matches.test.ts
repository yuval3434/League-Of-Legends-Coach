import { describe, expect, it } from "vitest";

import { gameLength, kda, queueName, result, roleName } from "./matches";

describe("match words", () => {
  it("writes a game's length as minutes and seconds", () => {
    expect(gameLength(1865)).toBe("31:05");
    expect(gameLength(59)).toBe("0:59");
  });

  it("names queues and roles, and keeps unknown ones visible", () => {
    expect(queueName(420)).toBe("Ranked Solo/Duo");
    expect(queueName(900)).toBe("Queue 900");
    expect(roleName("UTILITY")).toBe("Support");
    expect(roleName("")).toBe("—");
  });

  it("calls a remake a remake, whatever its win flag", () => {
    expect(result({ win: true, is_remake: true })).toBe("Remake");
    expect(result({ win: false, is_remake: false })).toBe("Loss");
  });

  it("shows kills, deaths and assists without a ratio", () => {
    expect(kda({ kills: 5, deaths: 0, assists: 7 })).toBe("5 / 0 / 7");
  });
});
