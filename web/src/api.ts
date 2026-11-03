// Types for the FastAPI responses, and the calls that fetch them. Every number
// the pages show comes from here: the frontend draws and formats, never computes.

export type Coverage = {
  player: {
    games: number;
    jungle_games: number;
    first_game: string;
    last_game: string;
    patches: string[];
  };
  champions: { champion: string; games: number }[];
};

export type CompareRow = {
  metric: string;
  theme: string | null;
  value: string;
  minute?: number;
  phase?: string;
  result?: string;
  objective?: string;
  higher_is_better: boolean;
  sample_unit: string;
  my_value: number | null;
  my_sample: number;
  my_low_sample: boolean;
  my_margin: number | null;
  benchmark_value: number | null;
  benchmark_sample: number;
  benchmark_margin: number | null;
  difference: number | null;
  // The gap as a whole percent of the benchmark, where that's meaningful.
  difference_pct: number | null;
  difference_margin: number | null;
  clear_gap: boolean | null;
  strong_gap: boolean | null;
  status: "ok" | "no_benchmark";
  // Shown beside its theme but never judged: no clear_gap, never a finding.
  context_only?: boolean;
};

export type Evidence = Pick<CompareRow, "metric" | "value" | "minute" | "phase">;

export type Finding = {
  direction: "behind" | "ahead";
  basis: "agreeing_metrics" | "strong_gap";
  rows: Evidence[];
};

export type ThemeStatus =
  | "finding"
  | "worth_watching"
  | "nothing_clear"
  | "no_margin"
  | "not_enough_data"
  | "no_benchmark"
  | "not_comparable";

export type Theme = {
  theme: string;
  status: ThemeStatus;
  findings?: Finding[];
  worth_watching?: Evidence[];
};

export type Comparison = {
  cohort: string;
  tier: string;
  status: "ok" | "no_benchmark";
  benchmark_games: number;
  benchmark_players: number;
  benchmark_patches: string[];
  rows: CompareRow[];
  themes: Theme[];
  notes: string[];
  not_comparable?: string[];
};

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function get<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, init);
  } catch {
    throw new ApiError(0, "Can't reach the API. Start it with: docker compose up -d");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, body.detail ?? `The API returned ${response.status}`);
  }
  return response.json() as Promise<T>;
}

/** The player a page is about, chosen by the server when no PUUID is given. */
export type Player = {
  puuid: string;
  game_name: string;
  tag_line: string;
  is_owner: boolean;
  rank_tier: string | null;
  rank_checked: boolean;
  main_role: string | null;
  // Each cohort, with why it doesn't fit this player, or null if it does.
  benchmarks: Record<string, string | null>;
};

/** A row of the player switcher. */
export type PlayerRow = Omit<Player, "rank_checked"> & {
  games: number;
  jungle_games: number;
  last_synced_at: string | null;
  rank_checked_at: string | null;
};

export type SyncStatus = {
  state: "idle" | "running" | "done" | "failed";
  riot_id?: string;
  stage?: "starting" | "account" | "match_list" | "rank" | "matches";
  done?: number;
  total?: number;
  // Matches that still need Riot calls: the ones the time left depends on.
  to_fetch?: number;
  error?: string;
  puuid?: string;
  matches_found?: number;
  matches_parsed?: number;
  matches_failed?: number;
};

export type Role = "TOP" | "JUNGLE" | "MIDDLE" | "BOTTOM" | "UTILITY";

/** One champion's totals from the champion_stats tool. */
export type ChampionRow = {
  champion: string;
  games: number;
  wins: number;
  win_rate_pct: number;
  // 95% margin and the range it gives, in whole percents; null on one game.
  margin_win_rate_pct: number | null;
  win_rate_low_pct: number | null;
  win_rate_high_pct: number | null;
  kills: number;
  deaths: number;
  assists: number;
  kda: number;
  cs_per_min: number;
  low_sample?: boolean;
};

/** What one coach call rested on, worked out by the server from the tool results. */
export type CoachTool = {
  name: string;
  arguments: Record<string, unknown>;
  error?: boolean;
  status?: string;
  your_games?: { min: number; max: number } | null;
  benchmark_games?: number;
  benchmark_players?: number;
  low_sample_rows?: number;
};

export type CoachStatus = "verified" | "unverified" | "refused" | "truncated" | "gave_up";

export type CoachAnswer = {
  text: string;
  status: CoachStatus;
  caught_numbers: string[];
  models: string[];
  tools: CoachTool[];
  cost_usd: number | null;
  cost_is_upper_bound: boolean;
};

/** A query string; parameters left null or undefined are left out. */
function query(params: Record<string, string | null | undefined>): string {
  const kept = Object.entries(params).filter((e): e is [string, string] => e[1] != null);
  return kept.length ? `?${new URLSearchParams(kept)}` : "";
}

const JSON_POST = { method: "POST", headers: { "Content-Type": "application/json" } };

// `player` is a PUUID from api.players(); null asks about the owner.
export const api = {
  coachStatus: () => get<{ available: boolean }>("/coach/status"),
  /** A paid call: one question to the coach, about one player. */
  ask: (question: string, player: string | null) =>
    get<CoachAnswer>("/coach", { ...JSON_POST, body: JSON.stringify({ question, player }) }),
  players: () => get<PlayerRow[]>("/players"),
  player: (player: string | null) => get<Player>(`/player${query({ player })}`),
  coverage: (player: string | null) => get<Coverage>(`/stats/data_coverage${query({ player })}`),
  champions: (role: Role | null, player: string | null) =>
    get<{ rows: ChampionRow[] }>(`/stats/champion_stats${query({ role, player })}`).then((r) => r.rows),
  compare: (cohort: "silver" | "emerald", player: string | null) =>
    get<Comparison>(`/benchmarks/compare${query({ cohort, player })}`),
  /** Starts a sync: free, but it uses the Riot call budget for a few minutes. */
  sync: (game_name: string, tag_line: string) =>
    get<SyncStatus>("/sync", { ...JSON_POST, body: JSON.stringify({ game_name, tag_line }) }),
  syncStatus: () => get<SyncStatus>("/sync/status"),
};
