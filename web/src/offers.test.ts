import { describe, expect, it } from "vitest";

import type { CohortOffer, RoleOffer } from "./api";
import { comparedWith, duration, groupName, peers, pullOfferShown, pullPlan, pullProgress } from "./offers";

describe("pullOfferShown", () => {
  it("hides the pull offer when no Riot key is set", () => {
    expect(pullOfferShown(false)).toBe(false);
  });
  it("shows it when a key is set", () => {
    expect(pullOfferShown(true)).toBe(true);
  });
  it("shows it while the key settings are unknown", () => {
    expect(pullOfferShown(null)).toBe(true);
  });
});

function offer(over: Partial<CohortOffer> = {}): CohortOffer {
  return {
    cohort: "gold_middle",
    tier: "GOLD",
    role: "MIDDLE",
    audience: "peers",
    games: 0,
    players: 0,
    checked: 0,
    has_benchmark: false,
    why_not: null,
    why_no_pull: null,
    to_500: { games_needed: 500, matches: 683, minutes: 91 },
    pull_more: { matches: 2000, minutes: 42 },
    ...over,
  };
}

describe("choosing cohorts", () => {
  it("compares with the first cohort that fits and has a benchmark", () => {
    const role: RoleOffer = {
      role: "JUNGLE",
      games: 40,
      cohorts: [
        offer({ cohort: "silver", has_benchmark: false }),
        offer({ cohort: "emerald", audience: "target", has_benchmark: true }),
      ],
    };
    expect(comparedWith(role)?.cohort).toBe("emerald");
    expect(peers(role)?.cohort).toBe("silver");
  });

  it("never compares with a cohort that doesn't fit", () => {
    const role: RoleOffer = { role: "JUNGLE", games: 40, cohorts: [offer({ has_benchmark: true, why_not: "Gold" })] };
    expect(comparedWith(role)).toBeNull();
  });
});

describe("pull words", () => {
  it("names the group", () => {
    expect(groupName("GOLD", "MIDDLE")).toBe("Gold mid laners");
    expect(groupName("SILVER", "UTILITY")).toBe("Silver supports");
  });

  it("gives the time in hours and minutes", () => {
    expect(duration(42)).toBe("about 42 minutes");
    expect(duration(91)).toBe("about 1 hour 31 minutes");
    expect(duration(120)).toBe("about 2 hours");
  });

  it("offers 500 games first, then Pull more", () => {
    const first = pullPlan(offer());
    expect(first.button).toBe("Pull a benchmark of Gold mid laners");
    expect(first.text).toContain("683 recent ranked matches for 500 games");
    expect(first.text).toContain("about 1 hour 31 minutes");

    const full = pullPlan(offer({ games: 500, to_500: { games_needed: 0, matches: 0, minutes: 0 } }));
    expect([full.button, full.more]).toEqual(["Pull more", true]);
    expect(full.text).toContain("2,000 more matches, about 42 minutes");
  });

  it("shows progress only for this cohort's pull", () => {
    const running = { state: "running", cohort: "gold_middle", mode: "to_500", started_checked: 0, checked: 120, games: 88 } as const;
    expect(pullProgress(running, offer())).toBe("Pulling: 88 of 500 games, from 120 matches checked.");
    expect(pullProgress({ ...running, cohort: "silver" }, offer())).toBeNull();
  });
});
