// Data for the Compare page: which rows go on the minute charts, and the
// headline. It picks and words the API's numbers; it computes no statistic.
//
// A role has at most two cohorts: its peers, players of the same rank, and for
// junglers below Emerald a target, Emerald junglers.

import type { CompareRow, Comparison } from "./api";
import { YOU, type Subject, verb, who as name, whoLower } from "./subject";

export const MINUTES = [10, 15, 20];

export type Slot = "peers" | "target";
export type Series = "you" | Slot;

/** One cohort on the page: its comparison and how it's named. */
export type Compared = { slot: Slot; short: string; group: string; comparison: Comparison };

/** One minute on a chart: each line's value and margin, with the rows behind them. */
export type MinutePoint = {
  minute: number;
  you: number | null;
  peers: number | null;
  target: number | null;
  // Band edges for drawing only: value ∓ margin, never shown as a number.
  youBand: [number, number] | null;
  peersBand: [number, number] | null;
  targetBand: [number, number] | null;
  peersRow?: CompareRow;
  targetRow?: CompareRow;
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

function usable(c: Maybe | undefined): Comparison | null {
  return c && c.status === "ok" ? c : null;
}

export function minutePoints(value: string, peers: Maybe, target: Maybe): MinutePoint[] {
  return MINUTES.map((minute) => {
    const p = usable(peers) ? minuteRow(peers!, value, minute) : undefined;
    const t = usable(target) ? minuteRow(target!, value, minute) : undefined;
    // Your value is the same in both comparisons; the peers' copy is used.
    const mine = p ?? t;
    return {
      minute,
      you: mine?.my_value ?? null,
      peers: p?.benchmark_value ?? null,
      target: t?.benchmark_value ?? null,
      youBand: band(mine?.my_value ?? null, mine?.my_margin ?? null),
      peersBand: band(p?.benchmark_value ?? null, p?.benchmark_margin ?? null),
      targetBand: band(t?.benchmark_value ?? null, t?.benchmark_margin ?? null),
      peersRow: p,
      targetRow: t,
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
export function compareHeadline(cohorts: Compared[], subject: Subject = YOU): string {
  const usableCohorts = cohorts.filter((c) => usable(c.comparison));
  if (!usableCohorts.length) return `No benchmark fits ${whoLower(subject)} yet`;
  for (const minute of [...MINUTES].reverse()) {
    const rows = usableCohorts.map((c) => ({ c, row: minuteRow(c.comparison, "avg_cs", minute) }));
    if (rows.some((r) => !r.row || r.row.my_low_sample)) continue;
    const amounts = rows.map((r) => ({ c: r.c, words: amount(r.row!) }));
    if (amounts.some((a) => !a.words)) continue;
    const [first, second] = amounts;
    const lead =
      first.words === "about the same"
        ? `about the same CS as ${first.c.group}`
        : `${first.words} CS than ${first.c.group}`;
    const rest = second
      ? second.words === "about the same"
        ? ` and about the same as ${second.c.short}`
        : ` and ${second.words} than ${second.c.short}`
      : "";
    return `At ${minute} minutes ${whoLower(subject)} ${verb(subject, "have")} ${lead}${rest}`;
  }
  return `${name(subject)} against ${usableCohorts.map((c) => c.group).join(" and ")}`;
}
