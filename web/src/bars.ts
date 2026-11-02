// Bar lengths for a measure card. A bar ends exactly at its value: the margin
// never changes a bar's length, so a smaller value always draws a shorter bar.
// Uncertainty is told by the verdict and the hover, not by the bar.

import type { CompareRow } from "./api";

export type BarLengths = { mine: number; theirs: number };

/** Pixel lengths of your bar and the benchmark's, both from zero; null when bars can't show the row. */
export function barLengths(row: CompareRow, plot: number): BarLengths | null {
  const { my_value: mine, benchmark_value: theirs } = row;
  // Gaps against an opponent can be negative: bars from zero can't show them.
  if (mine === null || theirs === null || mine < 0 || theirs < 0) return null;
  const max = Math.max(mine, theirs) || 1;
  return { mine: (mine / max) * plot, theirs: (theirs / max) * plot };
}
