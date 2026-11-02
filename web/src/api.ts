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

async function get<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`);
  } catch {
    throw new ApiError(0, "Can't reach the API. Start it with: docker compose up -d");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, body.detail ?? `The API returned ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export type Player = { game_name: string; tag_line: string };

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

export const api = {
  player: () => get<Player>("/player"),
  coverage: () => get<Coverage>("/stats/data_coverage"),
  champions: (role: Role | null) =>
    get<{ rows: ChampionRow[] }>(`/stats/champion_stats${role ? `?role=${role}` : ""}`).then((r) => r.rows),
  compare: (cohort: "silver" | "emerald") =>
    get<Comparison>(`/benchmarks/compare?cohort=${cohort}`),
};
