// Reading a Riot ID, and turning the server's sync status into a progress bar.

import type { SyncStatus } from "./api";

/**
 * Riot IDs are "Name#TAG": a name of 3 to 16 characters and a tag of 3 to 5
 * letters or digits. Returns the two parts, or why the text isn't one.
 */
export function parseRiotId(text: string): { name: string; tag: string } | { error: string } {
  const trimmed = text.trim();
  const at = trimmed.lastIndexOf("#");
  if (at < 0) return { error: "Add the tag after a #, like Name#EUW." };
  const name = trimmed.slice(0, at).trim();
  const tag = trimmed.slice(at + 1).trim();
  if (name.length < 3 || name.length > 16) return { error: "The name before the # has 3 to 16 characters." };
  if (!/^[\p{L}\p{N}]{3,5}$/u.test(tag)) return { error: "The tag after the # has 3 to 5 letters or digits." };
  return { name, tag };
}

// Two calls per match, and the development key allows 100 calls per 2 minutes.
export const SECONDS_PER_MATCH = 2.4;

export type Progress = { fraction: number; label: string; secondsLeft: number | null };

const STAGES: Record<string, string> = {
  starting: "Starting",
  account: "Looking up the Riot ID",
  match_list: "Listing their ranked matches",
  rank: "Checking their rank",
};

/** How far a running sync has got, in words and as a fraction for the bar. */
export function progressOf(status: SyncStatus): Progress {
  if (status.stage !== "matches" || !status.total) {
    return { fraction: 0, label: STAGES[status.stage ?? "starting"] ?? "Starting", secondsLeft: null };
  }
  const done = status.done ?? 0;
  const left = status.total - done;
  // Matches already stored cost no calls, so only the share still to fetch counts.
  const share = status.total ? (status.to_fetch ?? status.total) / status.total : 1;
  return {
    fraction: done / status.total,
    label: `${done} of ${status.total} matches`,
    secondsLeft: Math.round(left * share * SECONDS_PER_MATCH),
  };
}

/** "about 3 min left", "under a minute left". */
export function timeLeft(seconds: number | null): string {
  if (seconds === null) return "";
  if (seconds < 60) return "under a minute left";
  return `about ${Math.round(seconds / 60)} min left`;
}
