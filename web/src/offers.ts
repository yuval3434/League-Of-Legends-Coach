// Which cohort a role is compared with, which one can be pulled, and the words
// for a pull's estimate and progress. Every number comes from the server.

import type { CohortOffer, PullStatus, Role, RoleOffer } from "./api";

const GROUPS: Record<Role, string> = {
  TOP: "top laners",
  JUNGLE: "junglers",
  MIDDLE: "mid laners",
  BOTTOM: "bot laners",
  UTILITY: "supports",
};

const ROLE_TABS: Record<Role, string> = { TOP: "Top", JUNGLE: "Jungle", MIDDLE: "Mid", BOTTOM: "Bot", UTILITY: "Support" };

export function roleTab(role: Role): string {
  return ROLE_TABS[role];
}

const ROLE_WORDS: Record<Role, string> = { TOP: "top", JUNGLE: "jungle", MIDDLE: "mid", BOTTOM: "bot", UTILITY: "support" };

/** "mid", as in "12 mid games". */
export function roleWord(role: Role): string {
  return ROLE_WORDS[role];
}

/** "Gold mid laners". */
export function groupName(tier: string, role: Role): string {
  return `${tier.charAt(0)}${tier.slice(1).toLowerCase()} ${GROUPS[role]}`;
}

/** The cohort to compare with: the first that fits and has a benchmark, peers before a target. */
export function comparedWith(offer: RoleOffer): CohortOffer | null {
  return offer.cohorts.find((c) => c.why_not === null && c.has_benchmark) ?? null;
}

/** The peer cohort, which is the one offered for a pull. */
export function peers(offer: RoleOffer): CohortOffer | null {
  return offer.cohorts.find((c) => c.audience === "peers") ?? null;
}

/** "about 42 minutes", "about 1 hour 31 minutes". */
export function duration(minutes: number): string {
  if (minutes < 60) return `about ${minutes} minute${minutes === 1 ? "" : "s"}`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  const h = `${hours} hour${hours === 1 ? "" : "s"}`;
  return rest ? `about ${h} ${rest} minute${rest === 1 ? "" : "s"}` : `about ${h}`;
}

/** What pressing the button will do: reach 500 games, or "Pull more" past them. */
export function pullPlan(c: CohortOffer): { button: string; text: string; more: boolean } {
  const group = groupName(c.tier, c.role);
  if (c.to_500.games_needed > 0) {
    return {
      button: c.games ? `Finish the benchmark of ${group}` : `Pull a benchmark of ${group}`,
      text:
        `It checks about ${c.to_500.matches.toLocaleString("en")} recent ranked matches for ` +
        `${c.to_500.games_needed} games of ${group}: ${duration(c.to_500.minutes)}, at the rate our ` +
        "Silver pull measured.",
      more: false,
    };
  }
  return {
    button: "Pull more",
    text:
      `For champion benchmarks of ${group}: ${c.pull_more.matches.toLocaleString("en")} more matches, ` +
      `${duration(c.pull_more.minutes)}. Rare champions may still not reach 30 games.`,
    more: true,
  };
}

/** A running or finished pull of this cohort, in words. Null if the last pull was another cohort's. */
export function pullProgress(status: PullStatus, c: CohortOffer): string | null {
  if (status.cohort !== c.cohort) return null;
  const checked = (status.checked ?? 0) - (status.started_checked ?? 0);
  if (status.state === "failed") return `The pull stopped: ${status.error ?? "see the server log"}.`;
  if (status.mode === "to_500") {
    const line = `${status.games ?? 0} of 500 games, from ${checked.toLocaleString("en")} matches checked`;
    return status.state === "running" ? `Pulling: ${line}.` : `Done: ${line}.`;
  }
  const of = (status.max_matches ?? 0) - (status.started_checked ?? 0);
  const line = `${checked.toLocaleString("en")} of ${of.toLocaleString("en")} more matches checked`;
  return status.state === "running" ? `Pulling: ${line}.` : `Done: ${line}.`;
}
