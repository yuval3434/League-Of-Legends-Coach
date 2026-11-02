// A row's evidence state, read from the comparison's own verdicts. The page
// never decides what is clear: the API's themes do.

import type { CompareRow, Theme } from "./api";
import type { State } from "./components/Verdict";
import { sameRow } from "./metrics";

export function stateOf(row: CompareRow, themes: Theme[]): State {
  if (row.my_low_sample) return "low";
  for (const theme of themes) {
    for (const finding of theme.findings ?? []) {
      if (finding.rows.some((r) => sameRow(r, row))) return finding.direction;
    }
    if ((theme.worth_watching ?? []).some((r) => sameRow(r, row))) return "watching";
  }
  return "unclear";
}

/** A whole theme's state, from the API's verdict on it. */
export function themeState(theme: Theme): State {
  if (theme.status === "finding") return theme.findings?.some((f) => f.direction === "behind") ? "behind" : "ahead";
  if (theme.status === "worth_watching") return "watching";
  if (theme.status === "not_enough_data") return "low";
  return "unclear";
}
