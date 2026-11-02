// Data for the Compare page: which rows go on the minute charts, and the
// headline. It picks and words the API's numbers; it computes no statistic.

import type { CompareRow, Comparison } from "./api";

export const MINUTES = [10, 15, 20];

export type Series = "you" | "silver" | "emerald";

/** One minute on a chart: each line's value and margin, with the rows behind them. */
export type MinutePoint = {
  minute: number;
  you: number | null;
  silver: number | null;
  emerald: number | null;
  // Band edges for drawing only: value ∓ margin, never shown as a number.
  youBand: [number, number] | null;
  silverBand: [number, number] | null;
  emeraldBand: [number, number] | null;
  silverRow?: CompareRow;
  emeraldRow?: CompareRow;
};

export function minuteRow(comparison: Comparison, value: string, minute: number): CompareRow | undefined {
  return comparison.rows.find(
    (r) => r.value === value && r.minute === minute && (r.result ?? "all") === "all",
  );
}

function band(value: number | null, margin: number | null): [number, number] | null {
  return value === null || margin === null ? null : [value - margin, value + margin];
}

export function minutePoints(value: string, silver: Comparison, emerald: Comparison): MinutePoint[] {
  return MINUTES.map((minute) => {
    const s = minuteRow(silver, value, minute);
    const e = minuteRow(emerald, value, minute);
    // Your value is the same in both comparisons; Silver's copy is used.
    const mine = s ?? e;
    return {
      minute,
      you: mine?.my_value ?? null,
      silver: s?.benchmark_value ?? null,
      emerald: e?.benchmark_value ?? null,
      youBand: band(mine?.my_value ?? null, mine?.my_margin ?? null),
      silverBand: band(s?.benchmark_value ?? null, s?.benchmark_margin ?? null),
      emeraldBand: band(e?.benchmark_value ?? null, e?.benchmark_margin ?? null),
      silverRow: s,
      emeraldRow: e,
    };
  });
}

function amount(row: CompareRow): string | null {
  if (row.difference_pct === null || row.difference === null) return null;
  if (row.difference_pct === 0) return "about the same";
  return `${Math.abs(row.difference_pct)}% ${row.difference < 0 ? "less" : "more"}`;
}

/** "At 20 minutes you have 13% less CS than Silver junglers and 21% less than Emerald." */
export function compareHeadline(silver: Comparison, emerald: Comparison): string {
  for (const minute of [...MINUTES].reverse()) {
    const s = minuteRow(silver, "avg_cs", minute);
    const e = minuteRow(emerald, "avg_cs", minute);
    if (!s || !e || s.my_low_sample) continue;
    const a = amount(s);
    const b = amount(e);
    if (!a || !b) continue;
    const vsSilver = a === "about the same" ? "about the same CS as Silver junglers" : `${a} CS than Silver junglers`;
    const vsEmerald = b === "about the same" ? "about the same as Emerald" : `${b} than Emerald`;
    return `At ${minute} minutes you have ${vsSilver} and ${vsEmerald}`;
  }
  return "You against Silver and Emerald junglers";
}
