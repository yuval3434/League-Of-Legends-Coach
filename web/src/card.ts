// Words for the Draft page's champion card and the "Options for this draft"
// button. They word the API's numbers; they compute none.

import type { CardBenchmark, CardSide, OptionsEstimate } from "./api";
import { fmt } from "./metrics";

export type Cell = { main: string; detail: string; low: boolean };

// As precise as each stat is measured: CS per minute and deaths to 2 places,
// kill participation to 1, gold whole.
const DECIMALS: Record<string, number> = {
  cs_per_min: 2,
  gold_at_15: 0,
  deaths_early: 2,
  deaths_mid: 2,
  deaths_late: 2,
  kill_participation: 1,
};

function games(n: number): string {
  return `${n} game${n === 1 ? "" : "s"}`;
}

/** A value with its margin and games; greyed and "too early to tell" under 10. */
export function sideCell(stat: string, side: CardSide | null): Cell {
  if (!side) return { main: "—", detail: "no games", low: true };
  const places = DECIMALS[stat] ?? 1;
  const value = fmt(side.value, places);
  if (side.low_sample) return { main: value, detail: `too early to tell · ${games(side.games)}`, low: true };
  const margin = side.margin === null ? null : `give or take ${fmt(side.margin, places)}`;
  return { main: value, detail: [margin, games(side.games)].filter(Boolean).join(" · "), low: false };
}

/** A cohort's benchmark on one champion, or why there isn't one. */
export function benchmarkLines(b: CardBenchmark, rank: string, champion: string): { main: string; details: string[] } {
  const sample = `${b.benchmark_games} ${rank} game${b.benchmark_games === 1 ? "" : "s"} on ${champion} from ${b.benchmark_players} player${b.benchmark_players === 1 ? "" : "s"}`;
  if (b.status === "no_benchmark") return { main: "No benchmark", details: [`${sample}.`, b.note] };
  const patches = b.benchmark_patches.length > 1
    ? `patches ${b.benchmark_patches[0]} to ${b.benchmark_patches[b.benchmark_patches.length - 1]}`
    : `patch ${b.benchmark_patches[0]}`;
  const rate =
    b.win_rate === "not_comparable"
      ? `Win rate not compared: ${rank} junglers face ${rank} opponents.`
      : `Win rate ${fmt(b.win_rate.value, 1)}%, give or take ${fmt(b.win_rate.margin, 1)}.`;
  const cs = `CS per minute ${fmt(b.cs_per_min.value, 2)}, give or take ${fmt(b.cs_per_min.margin, 2)}.`;
  return { main: `${rank} junglers on ${champion}`, details: [rate, cs, `${sample}, ${patches}.`] };
}

/** Dollars, rounded up to the cent so "up to" stays true. */
export function upTo(usd: number): string {
  if (usd === 0) return "$0";
  if (usd < 0.01) return "under $0.01";
  return `$${(Math.ceil(usd * 100) / 100).toFixed(2)}`;
}

/** The ceiling, shown before anything is sent. */
export function estimateWords(e: OptionsEstimate, label: string): { main: string; detail: string } {
  if (e.input_tokens === null) {
    return { main: `Free on ${label}`, detail: "It runs on this computer: several minutes, and less reliable." };
  }
  return {
    main: `Up to ${upTo(e.max_cost_usd)} on ${label}`,
    detail:
      `${e.input_tokens.toLocaleString("en-GB")} input tokens, counted now; the answer is capped at ` +
      `${(e.max_output_tokens ?? 0).toLocaleString("en-GB")} tokens. That includes one retry if the number check ` +
      `asks for one; without it, up to ${upTo(e.one_call_max_usd ?? e.max_cost_usd)}.`,
  };
}
