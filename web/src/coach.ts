// Words for a coach reply's receipt: what it looked at, how many games that
// rested on, whether its numbers checked out, and what it cost. All of it
// comes from the server; the model's own text is never parsed here.

import type { CoachAnswer, CoachStatus, CoachTool } from "./api";

const TOOL_NAMES: Record<string, string> = {
  data_coverage: "What data there is",
  compare_to_benchmark: "Comparison with a rank",
  champion_stats: "Champion stats",
  win_rates: "Win rates",
  deaths_by_phase: "Deaths by phase",
  lane_diff: "Gold and CS against your opponent",
  win_rate_by_gold_diff: "Win rate by gold lead",
  after_loss_streak: "Games after a losing streak",
  cs_per_minute: "CS per minute",
  gold_cs_at_minute: "Gold and CS by minute",
  objective_control: "Objectives taken",
  deaths_before_objective: "Deaths before objectives",
  kill_participation: "Kill participation",
  wards_per_minute: "Wards per minute",
  first_lane_kill: "First kill in lane",
};

const ROLES: Record<string, string> = {
  TOP: "top",
  JUNGLE: "jungle",
  MIDDLE: "mid",
  BOTTOM: "bot",
  UTILITY: "support",
};

function capital(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** "Comparison with Silver, farm, on Viego": the tool and what it was asked for. */
export function toolLabel(tool: CoachTool, name: (id: string) => string = (id) => id): string {
  const base = TOOL_NAMES[tool.name] ?? tool.name;
  const { cohort, champion, theme, role } = tool.arguments as Record<string, string | null | undefined>;
  const parts: string[] = [];
  if (tool.name === "compare_to_benchmark" && cohort) parts.push(base.replace("a rank", capital(cohort)));
  else parts.push(base);
  if (theme) parts.push(theme === "economy" ? "farm" : theme);
  if (role) parts.push(ROLES[role] ?? role);
  if (champion) parts.push(`on ${name(champion)}`);
  return parts.join(", ");
}

function games(n: number): string {
  return `${n} game${n === 1 ? "" : "s"}`;
}

/** "Your 26–30 games · 500 benchmark games", or why there are none. */
export function sampleWords(tool: CoachTool): string {
  if (tool.error) return "The tool refused the request";
  if (tool.status === "no_benchmark") return "No benchmark for this yet";
  const parts: string[] = [];
  const mine = tool.your_games;
  if (mine) parts.push(mine.min === mine.max ? `your ${games(mine.max)}` : `your ${mine.min}–${mine.max} games`);
  if (tool.benchmark_games !== undefined) parts.push(`${tool.benchmark_games} benchmark games`);
  if (tool.low_sample_rows) parts.push(`${tool.low_sample_rows} under 10 games`);
  return parts.length ? capital(parts.join(" · ")) : "No games";
}

/** Did any of this answer rest on fewer than 10 of your games? */
export function restsOnFewGames(tool: CoachTool): boolean {
  return (tool.your_games?.min ?? 10) < 10 || (tool.low_sample_rows ?? 0) > 0;
}

export function costWords(answer: Pick<CoachAnswer, "cost_usd" | "cost_is_upper_bound">): string {
  if (answer.cost_usd === null) return "Cost unknown";
  const dollars = answer.cost_usd < 0.01 ? "under $0.01" : `$${answer.cost_usd.toFixed(3)}`;
  return answer.cost_is_upper_bound ? `At most ${dollars}` : dollars;
}

export const CHECK: Record<CoachStatus, { tone: "ok" | "warn" | "plain"; words: string }> = {
  verified: { tone: "ok", words: "Number check passed: every number above was found in the coach's data." },
  unverified: { tone: "warn", words: "Number check failed: these numbers weren't in the coach's data, so don't trust them:" },
  refused: { tone: "plain", words: "The coach couldn't answer this question." },
  truncated: { tone: "plain", words: "The answer was cut off. Try a narrower question." },
  gave_up: { tone: "plain", words: "The coach couldn't finish. Try a narrower question." },
};
