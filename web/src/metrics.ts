// Names, units and formatting for the comparison rows. Formatting shows a
// value at its own precision; it never re-rounds a number into a new one.

import type { CompareRow, Evidence, Role } from "./api";

export const THEME_NAMES: Record<string, string> = {
  economy: "Farm and gold",
  vision: "Vision",
  deaths: "Deaths",
  fights: "Kill participation",
  objectives: "Objectives",
};

type Key = Pick<CompareRow, "value" | "minute" | "phase" | "result" | "objective">;

const OBJECTIVES: Record<string, string> = {
  DRAGON: "Dragons",
  ELDER_DRAGON: "Elder Dragons",
  BARON_NASHOR: "Barons",
  RIFTHERALD: "Rift Heralds",
  HORDE: "Void Grubs",
};

// The phases deaths are counted in (analytics/stats.py: deaths_by_phase).
const PHASES: Record<string, string> = {
  early: "before 15 min",
  mid: "15–25 min",
  late: "after 25 min",
};

/** A row's name. `role` names the opponent in gold and CS differences. */
export function metricLabel(row: Key, role: Role = "JUNGLE"): string {
  const minute = row.minute ? `${row.minute} min` : "";
  const opponent = role === "JUNGLE" ? "enemy jungler" : "lane opponent";
  const split = row.result && row.result !== "all" ? `, ${row.result}s only` : "";
  switch (row.value) {
    case "avg_gold":
      return `Gold at ${minute}`;
    case "avg_cs":
      return `CS at ${minute}`;
    case "avg_cs_per_min":
      return "CS per minute";
    case "avg_gold_diff":
      return `Gold vs ${opponent}, ${minute}${split}`;
    case "avg_cs_diff":
      return `CS vs ${opponent}, ${minute}${split}`;
    case "avg_placed_per_min":
      return "Wards placed per minute";
    case "avg_control_placed_per_min":
      return "Control wards placed per minute";
    case "avg_trinket_placed_per_min":
      return "Trinket wards placed per minute";
    case "oracle_lens_pct":
      return "Games ending with Oracle Lens";
    case "avg_vision_score_per_min":
      return "Vision score per minute";
    case "avg_destroyed_per_min":
      return "Wards destroyed per minute";
    case "avg_deaths":
      return `Deaths per game, ${PHASES[row.phase ?? ""] ?? row.phase}`;
    case "avg_kill_participation_pct":
      return "Kill participation";
    case "avg_solo_kills":
      return "Solo kills per game";
    case "avg_solo_kills_before_15":
      return "Solo kills before 15 min";
    case "avg_lane_plates":
      return "Enemy plates in the lane, before 14 min";
    case "avg_my_plates":
      return "Plates last hit, before 14 min";
    case "avg_damage_share_pct":
      return "Share of the team's damage";
    case "avg_roam_takedowns":
      return "Takedowns away from mid, before 14 min";
    case "avg_support_item_placed_per_min":
      return "Support-item wards per minute";
    case "win_rate_pct":
      return "Win rate";
    case "team_share_pct":
      return OBJECTIVES[row.objective ?? ""] ?? row.objective ?? "Objective";
    default:
      return row.value;
  }
}

export function unit(value: string): string {
  if (value.endsWith("_pct")) return "%";
  return "";
}

/** The number of decimals a value was given with, so formatting keeps it. */
export function decimalsOf(n: number | null | undefined): number {
  if (n === null || n === undefined || Number.isInteger(n)) return 0;
  return String(n).split(".")[1]?.length ?? 0;
}

const MINUS = "−";

export function fmt(n: number | null | undefined, decimals = decimalsOf(n)): string {
  if (n === null || n === undefined) return "—";
  const text = Math.abs(n).toLocaleString("en-GB", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  return n < 0 ? `${MINUS}${text}` : text;
}

export function signed(n: number | null | undefined, decimals?: number): string {
  if (n === null || n === undefined) return "—";
  const text = fmt(n, decimals);
  return n > 0 ? `+${text}` : text;
}

/** Is "behind" the right word for this gap? More deaths is behind, too. */
export function isBehind(row: CompareRow): boolean {
  const d = row.difference ?? 0;
  return d !== 0 && d < 0 === row.higher_is_better;
}

/** The gap in plain words: "13% behind Silver", "4.9 CS behind", "1.3 points ahead", "13% fewer deaths". */
export function gapWords(row: CompareRow, cohort: string): string {
  const d = row.difference;
  if (d === null) return "";
  if (d === 0) return `level with ${cohort}`;
  const side = isBehind(row) ? `behind ${cohort}` : `ahead of ${cohort}`;
  const size = fmt(Math.abs(d), rowDecimals(row));
  if (row.value.endsWith("_diff")) return `${size} ${row.value.includes("gold") ? "gold" : "CS"} ${side}`;
  if (row.value.endsWith("_pct")) return `${size} points ${side}`;
  if (row.difference_pct === null) return "";
  if (row.difference_pct === 0) return `within 1% of ${cohort}`;
  // Deaths read better as counts than as a race: "13% fewer deaths than Silver".
  if (row.theme === "deaths") return `${Math.abs(row.difference_pct)}% ${d > 0 ? "more" : "fewer"} deaths than ${cohort}`;
  return `${Math.abs(row.difference_pct)}% ${side}`;
}

/** Decimals for a row: whatever its values were given with. */
export function rowDecimals(row: Pick<CompareRow, "my_value" | "benchmark_value">): number {
  return Math.max(decimalsOf(row.my_value), decimalsOf(row.benchmark_value));
}

export function sameRow(a: Evidence, b: Evidence): boolean {
  return (
    a.metric === b.metric &&
    a.value === b.value &&
    (a.minute ?? null) === (b.minute ?? null) &&
    (a.phase ?? null) === (b.phase ?? null)
  );
}

/** The full row (with margins) behind a theme's evidence entry. */
export function fullRow(rows: CompareRow[], evidence: Evidence): CompareRow | undefined {
  return rows.find(
    (row) => sameRow(row, evidence) && (row.result === undefined || row.result === "all"),
  );
}
