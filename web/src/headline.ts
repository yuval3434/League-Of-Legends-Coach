// The page's headline sentence, written by code from the comparison's findings.
// No model is involved, so the sentence can only say what the findings say.

import type { Evidence, Theme } from "./api";

function phrase(theme: string, rows: Evidence[]): string {
  if (theme === "economy") return "farm";
  if (theme === "vision") {
    const placed = rows.some((r) => r.value === "avg_placed_per_min");
    const destroyed = rows.some((r) => r.value === "avg_destroyed_per_min");
    if (placed && destroyed) return "vision";
    return placed ? "wards placed" : "wards destroyed";
  }
  if (theme === "deaths") return "deaths";
  if (theme === "fights") return "kill participation";
  return theme;
}

/** "a", "a, and on b", "a, b and c": short lists read as one sentence. */
function list(items: string[]): string {
  if (items.length <= 1) return items.join("");
  if (items.length === 2) return `${items[0]}, and on ${items[1]}`;
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

export function headline(themes: Theme[], who: string): string {
  const behind: string[] = [];
  const ahead: string[] = [];
  for (const theme of themes) {
    for (const finding of theme.findings ?? []) {
      const words = phrase(theme.theme, finding.rows);
      (finding.direction === "behind" ? behind : ahead).push(words);
    }
  }
  if (behind.length && ahead.length) {
    return `You're behind ${who} on ${list(behind)}, and ahead on ${list(ahead)}.`;
  }
  if (behind.length) return `You're behind ${who} on ${list(behind)}.`;
  if (ahead.length) return `You're ahead of ${who} on ${list(ahead)}.`;
  return `Nothing in your games stands out from ${who} yet.`;
}
