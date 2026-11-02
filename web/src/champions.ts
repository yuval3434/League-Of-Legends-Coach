// Sorting for the Champions table. It orders the API's rows; it computes nothing.

import type { ChampionRow } from "./api";

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
export function rangeWords(row: ChampionRow): string {
  const games = `${row.games} game${row.games === 1 ? "" : "s"}`;
  if (row.low_sample) return `too early to tell on ${games}`;
  if (row.win_rate_low_pct === null || row.win_rate_high_pct === null) return `no range on ${games}`;
  // Every game won or every game lost: the spread is zero, which isn't certainty.
  if (row.margin_win_rate_pct === 0) return `${games}, all ${row.wins ? "won" : "lost"}: too few to give a range`;
  return `could be anywhere from ${row.win_rate_low_pct}% to ${row.win_rate_high_pct}% on ${games}`;
}

/** A first click sorts names A to Z and numbers highest first. */
export function nextSort(current: Sort, key: SortKey): Sort {
  if (current.key === key) return { key, descending: !current.descending };
  return { key, descending: key !== "champion" };
}
