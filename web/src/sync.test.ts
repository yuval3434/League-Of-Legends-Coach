import { describe, expect, it } from "vitest";

import { parseRiotId, progressOf, timeLeft } from "./sync";

describe("Riot IDs", () => {
  it("splits a name and tag, keeping spaces in the name", () => {
    expect(parseRiotId(" Hide on bush#KR1 ")).toEqual({ name: "Hide on bush", tag: "KR1" });
  });

  it("uses the last # so a name can't hide a second tag", () => {
    expect(parseRiotId("Ana#B#EUW")).toEqual({ name: "Ana#B", tag: "EUW" });
  });

  it("says what's wrong", () => {
    expect(parseRiotId("NoTag")).toEqual({ error: "Add the tag after a #, like Name#EUW." });
    expect(parseRiotId("Al#EUW")).toHaveProperty("error");
    expect(parseRiotId("Ana#E")).toHaveProperty("error");
    expect(parseRiotId("Ana#EU-W")).toHaveProperty("error");
  });
});

describe("sync progress", () => {
  it("names the stage before matches are counted", () => {
    expect(progressOf({ state: "running", stage: "rank" })).toEqual({
      fraction: 0,
      label: "Checking their rank",
      secondsLeft: null,
    });
  });

  it("counts matches and the time left", () => {
    // 60 left of 100, all needing calls: 60 x 2.4 s.
    const p = progressOf({ state: "running", stage: "matches", done: 40, total: 100, to_fetch: 100 });
    expect(p.fraction).toBe(0.4);
    expect(p.label).toBe("40 of 100 matches");
    expect(p.secondsLeft).toBe(144);
  });

  it("doesn't count time for matches already stored", () => {
    // Half were stored already, so the 60 left take half as long.
    expect(progressOf({ state: "running", stage: "matches", done: 40, total: 100, to_fetch: 50 }).secondsLeft).toBe(72);
  });

  it("words the time left", () => {
    expect(timeLeft(144)).toBe("about 2 min left");
    expect(timeLeft(30)).toBe("under a minute left");
    expect(timeLeft(null)).toBe("");
  });
});
