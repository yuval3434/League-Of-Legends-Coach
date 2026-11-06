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
  role: Role;
  status: "ok" | "no_benchmark";
  benchmark_games: number;
  benchmark_players: number;
  benchmark_patches: string[];
  rows: CompareRow[];
  themes: Theme[];
  notes: string[];
  not_comparable?: string[];
};

/** Gold and CS gained minus the enemy jungler's, in one stretch of the game. */
export type JunglerStretch = {
  stretch: string;
  start_minute: number;
  end_minute: number;
  games: number;
  low_sample: boolean;
  avg_gold_diff: number | null;
  margin_gold_diff: number | null;
  avg_cs_diff: number | null;
  margin_cs_diff: number | null;
  clear_gold_diff: boolean | null;
  clear_cs_diff: boolean | null;
};

/** A cohort row for one stretch: like a comparison row, but never part of a theme. */
export type CohortStretch = Omit<CompareRow, "theme"> & { stretch: string };

export type StretchCohort = {
  cohort: string;
  tier: string;
  status: "ok" | "no_benchmark";
  benchmark_games: number;
  benchmark_players: number;
  rows: CohortStretch[];
  note?: string;
};

export type Stretches = {
  vs_enemy_jungler: JunglerStretch[];
  benchmarks: Record<"silver" | "emerald", StretchCohort>;
  notes: string[];
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
  // Ranked games per role, and the roles they get benchmarks in: main first.
  role_games: Record<string, number>;
  roles: Role[];
  // Each cohort, with why it doesn't fit this player, or null if it does.
  benchmarks: Record<string, string | null>;
};

/** One cohort that could fit a player in one role, and what pulling it takes. */
export type CohortOffer = {
  cohort: string;
  tier: string;
  role: Role;
  audience: "peers" | "target";
  games: number;
  players: number;
  checked: number;
  has_benchmark: boolean;
  // Why it doesn't fit the player, and why it can't be pulled now: null if it can.
  why_not: string | null;
  why_no_pull: string | null;
  to_500: { games_needed: number; matches: number; minutes: number };
  pull_more: { matches: number; minutes: number };
};

export type RoleOffer = { role: Role; games: number; cohorts: CohortOffer[] };

export type PullStatus = {
  state: "idle" | "running" | "done" | "failed";
  cohort?: string;
  mode?: "to_500" | "more" | "matches";
  max_matches?: number;
  started_checked?: number;
  checked?: number;
  games?: number;
  error?: string;
};

export type Offers = { roles: RoleOffer[]; pull: PullStatus };

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

/** A coach model the picker offers, with its estimated cost per question. */
export type CoachModel = {
  id: string;
  label: string;
  estimated_cost_usd: number;
  available: boolean;
  // Why it can't answer right now, such as a missing key or Ollama not running.
  reason: string | null;
  default: boolean;
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

/** What the settings page may know about a key. The key itself never leaves the server. */
export type KeyInfo = {
  set: boolean;
  last4: string | null;
  set_at: string | null;
  // Riot only: development keys expire 24 hours after they're made.
  expires_at?: string | null;
};
export type KeyName = "riot" | "anthropic";

// Only our own page sends this header; the API refuses settings requests without it.
const SETTINGS = { "X-LoLCoach-Settings": "1" };

/** A query string; parameters left null or undefined are left out. */
function query(params: Record<string, string | null | undefined>): string {
  const kept = Object.entries(params).filter((e): e is [string, string] => e[1] != null);
  return kept.length ? `?${new URLSearchParams(kept)}` : "";
}

const JSON_POST = { method: "POST", headers: { "Content-Type": "application/json" } };

/** One of the player's games, for the Matches list. */
export type MatchRow = {
  match_id: string;
  game_start_at: string;
  duration_s: number;
  patch: string;
  queue_id: number;
  is_remake: boolean;
  champion: string;
  role: string;
  win: boolean;
  kills: number;
  deaths: number;
  assists: number;
  cs: number;
};

/** One player in a game: champion, role and stats, never a name. */
export type MatchPlayer = {
  side: "ally" | "enemy";
  is_me: boolean;
  role: string;
  champion: string;
  win: boolean;
  kills: number;
  deaths: number;
  assists: number;
  cs: number;
  cs_per_min: number;
  gold_earned: number;
  damage_to_champions: number;
  vision_score: number;
};

export type MatchDetail = Omit<MatchRow, "champion" | "role" | "win" | "kills" | "deaths" | "assists" | "cs"> & {
  players: MatchPlayer[];
};

/** One side of a card row: the champion's games, or all jungle games. */
export type CardSide = { value: number; margin: number | null; games: number; low_sample: boolean };

export type CardRow = { stat: string; label: string; champion: CardSide | null; overall: CardSide | null };

type Measured = { value: number; margin: number | null };

export type CardBenchmark = {
  cohort: "silver" | "emerald";
  tier: string;
  benchmark_games: number;
  benchmark_players: number;
} & (
  | { status: "no_benchmark"; note: string }
  | {
      status: "ok";
      benchmark_patches: string[];
      cs_per_min: Measured;
      win_rate: Measured | "not_comparable";
    }
);

/** Riot's own text about a champion, from Data Dragon. */
export type RiotText = {
  title: string;
  abilities: { key: string; name: string; description: string }[];
  ally_tips: string[];
  enemy_tips: string[];
};

export type ChampionCard = {
  champion: string;
  games: number;
  low_sample: boolean;
  last_played: string | null;
  rows: CardRow[];
  benchmarks: Record<"silver" | "emerald", CardBenchmark>;
  riot: RiotText | null;
  notes: string[];
};

export type RiotNotes = {
  data_dragon_version: string;
  champions: ({ champion: string; name: string } & Partial<RiotText>)[];
  note: string;
};

/** The most "Options for this draft" can cost on a board, counted before it's sent. */
export type OptionsEstimate = {
  model: string;
  champions: string[];
  input_tokens: number | null;
  max_output_tokens: number | null;
  max_cost_usd: number;
  one_call_max_usd?: number;
};

/** Auto-sync's last round, or why it isn't running. */
export type AutoSync = {
  state: "off" | "waiting" | "running" | "ok" | "partly_failed" | "skipped" | "key_refused" | "no_key" | "failed";
  every_minutes: number;
  last_run_at?: string;
  players?: number;
  new_games?: number;
  failed?: string[];
  error?: string;
};

/** A champion from Data Dragon, for the champion-select picker. */
export type DraftChampion = { champion: string; name: string; tags: string[] };

/** What champion select shows: champions only, never a player. */
export type Board = { allies: string[]; enemies: string[]; bans: string[] };

export type GapId = "no_frontline" | "no_magic_damage" | "no_physical_damage";

type Described = {
  champion: string;
  name: string;
  tags: string[];
  damage: "physical" | "magic" | "mixed";
  attack_rating: number;
  magic_rating: number;
};

/** One of the player's jungle champions (3+ games), in the API's order: most played first. */
export type PoolEntry = Partial<Described> & {
  champion: string;
  games: number;
  wins: number;
  win_rate_pct: number;
  margin_win_rate_pct?: number;
  low_sample?: boolean;
  fills?: GapId[];
  unavailable?: "picked" | "banned";
};

/** The enemy's damage mix and frontline, by the same rules as the gaps. */
export type EnemyComposition = {
  picked: number;
  damage: Record<"physical" | "magic" | "mixed", number>;
  // null under 3 picks.
  mix: "mostly_physical" | "mostly_magic" | "mixed" | null;
  tanks: string[];
  // Fighters that aren't also tanks.
  fighters: string[];
  has_frontline: boolean;
  // General game knowledge, not from the player's games.
  general_advice?: { text: string; source: string };
};

export type DraftBoard = {
  your_team: Described[];
  enemy_team: Described[];
  enemy_composition: EnemyComposition | null;
  bans: string[];
  rules_checked: string[];
  gaps: { gap: GapId; description: string; filled_by: string[] }[];
  pool: PoolEntry[];
  matchups: string;
  notes: string[];
  data_dragon_version: string;
};

// `player` is a PUUID from api.players(); null asks about the owner.
export const api = {
  coachStatus: () => get<{ available: boolean }>("/coach/status"),
  coachModels: () => get<CoachModel[]>("/coach/models"),
  /** One question to the coach, about one player. Paid, unless `model` is the local one. */
  ask: (question: string, player: string | null, model: string | null) =>
    get<CoachAnswer>("/coach", { ...JSON_POST, body: JSON.stringify({ question, player, model }) }),
  players: () => get<PlayerRow[]>("/players"),
  player: (player: string | null) => get<Player>(`/player${query({ player })}`),
  coverage: (player: string | null) => get<Coverage>(`/stats/data_coverage${query({ player })}`),
  champions: (role: Role | null, player: string | null) =>
    get<{ rows: ChampionRow[] }>(`/stats/champion_stats${query({ role, player })}`).then((r) => r.rows),
  compare: (cohort: string, player: string | null) =>
    get<Comparison>(`/benchmarks/compare${query({ cohort, player })}`),
  stretches: (player: string | null) => get<Stretches>(`/benchmarks/stretches${query({ player })}`),
  matches: (player: string | null, offset = 0) =>
    get<{ matches: MatchRow[]; total: number }>(`/matches${query({ player, offset: String(offset) })}`),
  match: (id: string, player: string | null) =>
    get<MatchDetail>(`/matches/${encodeURIComponent(id)}${query({ player })}`),
  championCard: (champion: string, player: string | null) =>
    get<ChampionCard>(`/draft/champion/${encodeURIComponent(champion)}${query({ player })}`),
  riot: (champions: string[]) => get<RiotNotes>(`/draft/riot${query({ champions: champions.join(",") })}`),
  /** Free: counts the tokens, sends nothing to a model. */
  optionsEstimate: (board: Board, player: string | null, model: string) =>
    get<OptionsEstimate>("/draft/options/estimate", {
      ...JSON_POST,
      body: JSON.stringify({ ...board, player, model }),
    }),
  /** Paid, unless the local model answers. */
  options: (board: Board, player: string | null, model: string) =>
    get<CoachAnswer & { champions: string[] }>("/draft/options", {
      ...JSON_POST,
      body: JSON.stringify({ ...board, player, model }),
    }),
  draftChampions: () => get<{ version: string; champions: DraftChampion[] }>("/draft/champions"),
  /** The champion-select board for what's on screen. Free: no model call. */
  draft: (board: Board, player: string | null) =>
    get<DraftBoard>("/draft", { ...JSON_POST, body: JSON.stringify({ ...board, player }) }),
  /** Starts a sync: free, but it uses the Riot call budget for a few minutes. */
  sync: (game_name: string, tag_line: string) =>
    get<SyncStatus>("/sync", { ...JSON_POST, body: JSON.stringify({ game_name, tag_line }) }),
  syncStatus: () => get<SyncStatus>("/sync/status"),
  autoSync: () => get<AutoSync>("/sync/auto"),
  /** Each of the player's roles, its cohorts, and what a pull would take. Free. */
  offers: (player: string | null) => get<Offers>(`/benchmarks/offers${query({ player })}`),
  /** Starts a pull: free, but it uses the Riot call budget for an hour or more. */
  pull: (cohort: string, player: string | null, more: boolean) =>
    get<PullStatus>("/benchmarks/pull", { ...JSON_POST, body: JSON.stringify({ cohort, player, more }) }),
  pullStatus: () => get<PullStatus>("/benchmarks/status"),
  keys: () => get<Record<KeyName, KeyInfo>>("/settings/keys", { headers: SETTINGS }),
  /** Tests the key with one cheap call; it's only saved if that works. */
  setKey: (name: KeyName, key: string) =>
    get<KeyInfo>(`/settings/keys/${name}`, {
      method: "PUT",
      headers: { ...SETTINGS, "Content-Type": "application/json" },
      body: JSON.stringify({ key }),
    }),
};
