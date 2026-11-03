// Sorting for the Champions table. It orders the API's rows; it computes nothing.

import type { ChampionRow } from "./api";
import { YOU, type Subject, who, whose } from "./subject";

export type SortKey = "champion" | "games" | "win_rate_pct" | "kda" | "cs_per_min";
export type Sort = { key: SortKey; descending: boolean };

/** Sorted by one column; ties go to the most played, then by name, so the order is stable. */
export function sortChampions(rows: ChampionRow[], sort: Sort, name: (id: string) => string = (id) => id): ChampionRow[] {
  const sign = sort.descending ? -1 : 1;
  return [...rows].sort((a, b) => {
    const first =
      sort.key === "champion"
        ? name(a.champion).localeCompare(name(b.champion))
        : a[sort.key] - b[sort.key];
    return sign * first || b.games - a.games || name(a.champion).localeCompare(name(b.champion));
  });
}

/** The win rate's range in plain words, for the hover. */
export function rangeWords(row: ChampionRow, subject: Subject = YOU): string {
  const record = `${who(subject)} won ${row.wins} of ${row.games}.`;
  const them = subject.you ? "you really are" : `${subject.name} really is`;
  const tooFew = `That's too few games to tell how good ${them} on this champion`;
  // Under 10 games, or a record with no spread (all won or all lost), a range would mislead.
  if (row.low_sample || row.win_rate_low_pct === null || row.win_rate_high_pct === null || row.margin_win_rate_pct === 0) {
    return `${record} ${tooFew}.`;
  }
  return `${record} ${tooFew} — ${whose(subject)} true win rate could be anywhere from about ${row.win_rate_low_pct}% to ${row.win_rate_high_pct}%.`;
}

/** A first click sorts names A to Z and numbers highest first. */
export function nextSort(current: Sort, key: SortKey): Sort {
  if (current.key === key) return { key, descending: !current.descending };
  return { key, descending: key !== "champion" };
}
