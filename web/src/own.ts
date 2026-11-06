// A player's own numbers in one role, when no benchmark fits yet: every value
// and margin comes from the server; this only picks words for them.

import type { OwnRow } from "./api";

/** The measures worth a row: averages and shares. Rates without a margin stay out. */
export function shownRows(rows: OwnRow[]): OwnRow[] {
  return rows.filter((r) => r.value.startsWith("avg_"));
}

/** What wins against losses says for one measure. */
export function winLossWords(row: OwnRow): string {
  if (row.context_only) return "Context, not judged";
  if (row.wins.low_sample || row.losses.low_sample) return "Too early to tell";
  if (row.clear_gap === null) return "No margin";
  if (!row.clear_gap || row.difference === null) return "No clear difference";
  return row.difference > 0 ? "Clearly higher in wins" : "Clearly lower in wins";
}
