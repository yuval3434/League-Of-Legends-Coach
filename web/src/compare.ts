// Data for the Compare page: which rows go on the minute charts, and the
// headline. It picks and words the API's numbers; it computes no statistic.

import type { CompareRow, Comparison } from "./api";
import { YOU, type Subject, verb, who as name, whoLower } from "./subject";

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

/** A cohort's comparison, or null when there's no benchmark for this player. */
export type Maybe = Comparison | null;

function usable(c: Maybe): Comparison | null {
  return c && c.status === "ok" ? c : null;
}

export function minutePoints(value: string, silver: Maybe, emerald: Maybe): MinutePoint[] {
  return MINUTES.map((minute) => {
    const s = usable(silver) ? minuteRow(silver!, value, minute) : undefined;
    const e = usable(emerald) ? minuteRow(emerald!, value, minute) : undefined;
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

/**
 * "At 20 minutes you have 13% less CS than Silver junglers and 21% less than
 * Emerald." Only cohorts with a benchmark for this player are named.
 */
export function compareHeadline(silver: Maybe, emerald: Maybe, subject: Subject = YOU): string {
  const cohorts = [
    { name: "Silver", c: usable(silver) },
    { name: "Emerald", c: usable(emerald) },
  ].filter((x): x is { name: string; c: Comparison } => x.c !== null);
  if (!cohorts.length) return `No benchmark fits ${whoLower(subject)} yet`;
  for (const minute of [...MINUTES].reverse()) {
    const rows = cohorts.map(({ name: cohort, c }) => ({ cohort, row: minuteRow(c, "avg_cs", minute) }));
    if (rows.some((r) => !r.row || r.row.my_low_sample)) continue;
    const amounts = rows.map((r) => ({ cohort: r.cohort, words: amount(r.row!) }));
    if (amounts.some((a) => !a.words)) continue;
    const [first, second] = amounts;
    const lead =
      first.words === "about the same"
        ? `about the same CS as ${first.cohort} junglers`
        : `${first.words} CS than ${first.cohort} junglers`;
    const rest = second
      ? second.words === "about the same"
        ? ` and about the same as ${second.cohort}`
        : ` and ${second.words} than ${second.cohort}`
      : "";
    return `At ${minute} minutes ${whoLower(subject)} ${verb(subject, "have")} ${lead}${rest}`;
  }
  return `${name(subject)} against ${cohorts.map((c) => c.name).join(" and ")} junglers`;
}
