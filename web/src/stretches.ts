// Words for the stretch table on the Compare page: gold and CS lost to the enemy
// jungler, and against each cohort, from 0-10, 10-15 and 15-20 minutes. It words
// the API's numbers; it computes none.

import type { CohortStretch, JunglerStretch, StretchCohort } from "./api";
import { fmt, rowDecimals } from "./metrics";

export const STRETCHES = [
  { id: "0-10", label: "0–10 min" },
  { id: "10-15", label: "10–15 min" },
  { id: "15-20", label: "15–20 min" },
] as const;

export type Unit = "gold" | "cs";

// Clear, could be chance, or too few games to say. Stretch rows never make a
// finding, so none of these uses the accent colour.
export type Tone = "clear" | "unclear" | "low";

export type Cell = { main: string; detail: string; tone: Tone };

const WORD: Record<Unit, string> = { gold: "gold", cs: "CS" };

function games(n: number): string {
  return `${n} game${n === 1 ? "" : "s"}`;
}

function tooFew(n: number): Cell {
  return { main: "Too few games", detail: games(n), tone: "low" };
}

const NONE: Cell = { main: "No benchmark", detail: "", tone: "low" };

/** "Lost 219 gold", give or take 111, on 85 games: against the enemy jungler. */
export function junglerCell(row: JunglerStretch | undefined, unit: Unit): Cell {
  if (!row) return { main: "No games", detail: "", tone: "low" };
  if (row.low_sample) return tooFew(row.games);
  const value = unit === "gold" ? row.avg_gold_diff : row.avg_cs_diff;
  const margin = unit === "gold" ? row.margin_gold_diff : row.margin_cs_diff;
  const clear = unit === "gold" ? row.clear_gold_diff : row.clear_cs_diff;
  if (value === null) return { main: "—", detail: games(row.games), tone: "low" };
  const main =
    value < 0
      ? `Lost ${fmt(Math.abs(value))} ${WORD[unit]}`
      : value > 0
        ? `Gained ${fmt(value)} ${WORD[unit]}`
        : "Even";
  const parts = [margin === null ? null : `give or take ${fmt(margin)}`, games(row.games)];
  if (!clear) parts.push("could be chance");
  return { main, detail: parts.filter(Boolean).join(" · "), tone: clear ? "clear" : "unclear" };
}

export function cohortRow(cohort: StretchCohort | undefined, stretch: string, unit: Unit): CohortStretch | undefined {
  const value = unit === "gold" ? "avg_gold_gained" : "avg_cs_gained";
  return cohort?.rows.find((r) => r.stretch === stretch && r.value === value);
}

/** "244 less gold than Silver", give or take 89, on 85 games against 499. */
export function cohortCell(cohort: StretchCohort | undefined, stretch: string, unit: Unit, name: string): Cell {
  if (!cohort || cohort.status !== "ok") return NONE;
  const row = cohortRow(cohort, stretch, unit);
  if (!row || row.status !== "ok") return NONE;
  if (row.my_low_sample) return tooFew(row.my_sample);
  const d = row.difference;
  if (d === null) return { main: "—", detail: "", tone: "low" };
  // Shown as precisely as the values themselves: whole gold, CS to one decimal.
  const places = rowDecimals(row);
  const main =
    d < 0
      ? `${fmt(Math.abs(d), places)} less ${WORD[unit]} than ${name}`
      : d > 0
        ? `${fmt(d, places)} more ${WORD[unit]} than ${name}`
        : `Same as ${name}`;
  const parts = [
    row.difference_margin === null ? null : `give or take ${fmt(row.difference_margin, places)}`,
    `${games(row.my_sample)} against ${row.benchmark_sample}`,
  ];
  if (!row.clear_gap) parts.push("could be chance");
  return { main, detail: parts.filter(Boolean).join(" · "), tone: row.clear_gap ? "clear" : "unclear" };
}
