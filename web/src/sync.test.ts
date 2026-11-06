import { describe, expect, it } from "vitest";

import { autoSyncWords, parseRiotId, progressOf, timeLeft } from "./sync";

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

describe("auto-sync", () => {
  const clock = () => "11:52";

  it("says when it last ran and what it found", () => {
    expect(autoSyncWords({ state: "ok", every_minutes: 30, last_run_at: "x", players: 2, new_games: 1 }, clock)).toEqual({
      text: "Auto-sync every 30 minutes. Last at 11:52: 1 new game.",
      warn: false,
    });
    const partly = autoSyncWords(
      { state: "partly_failed", every_minutes: 30, last_run_at: "x", new_games: 0, failed: ["Ana#EUW wasn't found"] },
      clock,
    );
    expect(partly.text).toBe("Auto-sync every 30 minutes. Last at 11:52: 0 new games. Couldn't sync: Ana#EUW wasn't found.");
  });

  it("warns when the key is refused, in the server's words", () => {
    const words = autoSyncWords({ state: "key_refused", every_minutes: 30, error: "Riot refused the API key." }, clock);
    expect(words).toEqual({ text: "Riot refused the API key.", warn: true });
  });

  it("doesn't warn about a skipped round", () => {
    const words = autoSyncWords({ state: "skipped", every_minutes: 30, error: "A manual sync was running." }, clock);
    expect(words).toEqual({ text: "Auto-sync every 30 minutes. The last round was skipped: a manual sync was running.", warn: false });
  });
});
