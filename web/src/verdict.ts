// Plain-language verdicts. The margin decides which word applies; the word is
// what a player reads first, and the margin waits behind a hover.

import type { State } from "./components/Verdict";

export const PLAIN: Record<State, string> = {
  behind: "Clearly behind",
  ahead: "Clearly ahead",
  watching: "Might be a gap",
  unclear: "No clear difference",
  low: "Too early to tell",
};

export const PLAIN_TONE: Record<State, string> = {
  behind: "text-accent",
  ahead: "text-ink",
  watching: "text-ink2",
  unclear: "text-ink2",
  low: "text-ink3",
};
