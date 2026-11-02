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
