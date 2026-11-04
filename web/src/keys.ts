// A stored key's status in words. The page only ever has the last 4 characters.

import type { KeyInfo } from "./api";

export type KeyStatus = { tone: "ok" | "warn" | "off"; words: string };

function hours(ms: number): number {
  return Math.max(0, Math.round(ms / 3_600_000));
}

/** "Set, ending …abcd · expires in 21 h", or why it needs attention. */
export function keyStatus(info: KeyInfo, now: Date = new Date()): KeyStatus {
  if (!info.set) return { tone: "off", words: "Not set" };
  const ending = info.last4 ? `ending …${info.last4}` : "set";
  if (info.expires_at) {
    const left = new Date(info.expires_at).getTime() - now.getTime();
    if (left <= 0) return { tone: "warn", words: `${ending} · expired ${hours(-left)} h ago` };
    const soon = left < 2 * 3_600_000;
    return { tone: soon ? "warn" : "ok", words: `${ending} · expires in ${left < 3_600_000 ? "under 1" : hours(left)} h` };
  }
  if (info.set_at === null && info.expires_at === null) {
    // A Riot key that was in .env before the settings page existed: its age isn't known.
    return { tone: "ok", words: `${ending} · set before this page, so its expiry isn't known` };
  }
  return { tone: "ok", words: ending };
}

export function shortTime(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}
