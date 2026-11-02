import { useEffect, useState } from "react";

import { api, type CompareRow, type Comparison, type Coverage, type Player, type Theme } from "../api";
import { Layout } from "../components/Layout";
import { MeasureCard } from "../components/MeasureCard";
import { ProfileHeader } from "../components/ProfileHeader";
import { Marker, type State } from "../components/Verdict";
import { headline } from "../headline";
import { fmt, metricLabel } from "../metrics";
import { stateOf } from "../state";
import { PLAIN, PLAIN_TONE } from "../verdict";

const COHORT = "Silver";
const WHO = "Silver junglers";

type Key = { value: string; minute?: number; phase?: string };

const TOPIC: Record<string, string> = {
  economy: "farm",
  vision: "vision",
  deaths: "deaths",
  fights: "kill participation",
  objectives: "objectives",
};

// The few measures that tell a theme's story; the rest wait behind "Show all".
const TELLING: Record<string, Key[]> = {
  economy: [{ value: "avg_cs_per_min" }, { value: "avg_cs", minute: 15 }, { value: "avg_gold", minute: 15 }],
  vision: [{ value: "avg_placed_per_min" }, { value: "avg_destroyed_per_min" }],
  deaths: [
    { value: "avg_deaths", phase: "early" },
    { value: "avg_deaths", phase: "mid" },
    { value: "avg_deaths", phase: "late" },
  ],
  fights: [{ value: "avg_kill_participation_pct" }],
};

const BEHIND: Record<string, string> = {
  economy: "You farm less than",
  deaths: "You die more than",
  fights: "You take part in fewer of your team's kills than",
};
const AHEAD: Record<string, string> = {
  economy: "You farm more than",
  deaths: "You die less than",
  fights: "You take part in more of your team's kills than",
};

function matches(row: CompareRow, key: Key): boolean {
  return (
    row.value === key.value &&
    (row.minute ?? null) === (key.minute ?? null) &&
    (row.phase ?? null) === (key.phase ?? null) &&
    (row.result ?? "all") === "all"
  );
}

function capital(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function sectionState(theme: Theme): State {
  if (theme.status === "finding") return theme.findings?.some((f) => f.direction === "behind") ? "behind" : "ahead";
  if (theme.status === "worth_watching") return "watching";
  if (theme.status === "not_enough_data") return "low";
  return "unclear";
}

function title(theme: Theme): string {
  const topic = TOPIC[theme.theme] ?? theme.theme;
  if (theme.status === "finding") {
    const finding = theme.findings?.find((f) => f.direction === "behind") ?? theme.findings![0];
    if (theme.theme === "vision") {
      const placed = finding.rows.some((r) => r.value === "avg_placed_per_min");
      const more = finding.direction === "ahead";
      return `You ${placed ? "place" : "destroy"} ${more ? "more" : "fewer"} wards than ${WHO}`;
    }
    const lead = (finding.direction === "behind" ? BEHIND : AHEAD)[theme.theme];
    return lead ? `${lead} ${WHO}` : capital(topic);
  }
  switch (theme.status) {
    case "worth_watching":
      return `Might be a gap in ${topic}`;
    case "nothing_clear":
      return `No clear difference in ${topic}`;
    case "no_margin":
      return `${capital(topic)} can't be judged yet`;
    case "not_enough_data":
      return `Too early to tell on ${topic}`;
    case "no_benchmark":
      return `No benchmark for ${topic}`;
    default:
      return `${capital(topic)} isn't compared with this cohort`;
  }
}

function explanation(theme: Theme): string {
  const topic = TOPIC[theme.theme] ?? theme.theme;
  if (theme.status === "finding") {
    const finding = theme.findings?.find((f) => f.direction === "behind") ?? theme.findings![0];
    if (finding.basis === "strong_gap") return "One gap is far bigger than chance would explain.";
    const measures = new Set(finding.rows.map((r) => r.value)).size;
    return `${measures} ${topic} measures point the same way, so this isn't chance.`;
  }
  switch (theme.status) {
    case "worth_watching":
      return "One measure shows a gap, but on its own it could be chance.";
    case "nothing_clear":
      return `Your numbers and ${COHORT}'s overlap, so any gap here could be chance.`;
    case "no_margin":
      return "These stats don't have a margin yet, so no verdict is given.";
    default:
      return "";
  }
}

function SectionHead({
  label,
  heading,
  note,
  state,
  verdict,
}: {
  label: string;
  heading: string;
  note: string;
  state: State;
  verdict?: string;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-3">
      <div className="max-w-[760px]">
        <div className="smallcaps text-ink3">{label}</div>
        <h2 className={`display mt-1.5 text-[30px] leading-[1.1] ${state === "unclear" || state === "low" ? "text-ink2" : "text-ink"}`}>
          {heading}
        </h2>
        {note && <p className="mt-2 text-[15px] text-ink2">{note}</p>}
      </div>
      <span className={`inline-flex items-center gap-2 pb-1 text-[14px] font-medium ${PLAIN_TONE[state]}`}>
        <Marker state={state} size={8} />
        {verdict ?? PLAIN[state]}
      </span>
    </div>
  );
}

function ThemeSection({ theme, rows, themes }: { theme: Theme; rows: CompareRow[]; themes: Theme[] }) {
  const [open, setOpen] = useState(false);
  const telling = (TELLING[theme.theme] ?? [])
    .map((key) => rows.find((r) => matches(r, key)))
    .filter((r): r is CompareRow => r !== undefined);
  const rest = rows.filter(
    (r) => r.theme === theme.theme && (r.result ?? "all") === "all" && r.clear_gap !== null && !telling.includes(r),
  );
  const shown = open ? [...telling, ...rest] : telling;
  const topic = TOPIC[theme.theme] ?? theme.theme;
  const objectives = theme.theme === "objectives" ? rows.filter((r) => r.theme === "objectives" && r.value === "team_share_pct") : [];

  return (
    <section className="mt-16">
      <SectionHead
        label={capital(topic)}
        heading={title(theme)}
        note={explanation(theme)}
        state={sectionState(theme)}
        verdict={theme.status === "no_margin" ? "No verdict yet" : undefined}
      />
      {shown.length > 0 && (
        <div className="mt-6 grid gap-x-10 gap-y-2 md:grid-cols-2 xl:grid-cols-3">
          {shown.map((row) => (
            <MeasureCard key={metricLabel(row)} row={row} state={stateOf(row, themes)} cohort={COHORT} />
          ))}
        </div>
      )}
      {objectives.length > 0 && (
        <div className="mt-5 flex flex-wrap gap-x-10 gap-y-2 text-[14px] text-ink3">
          {objectives.map((r) => (
            <span key={r.objective}>
              {metricLabel(r)}: your team took {fmt(r.my_value)}% of {r.my_sample} · {COHORT} {fmt(r.benchmark_value)}%
            </span>
          ))}
        </div>
      )}
      {rest.length > 0 && (
        <button
          onClick={() => setOpen(!open)}
          className="mt-5 text-[13px] text-ink2 underline decoration-rule underline-offset-4 hover:text-ink hover:decoration-ink3"
        >
          {open ? `Show the main ${telling.length}` : `Show all ${telling.length + rest.length} ${topic} measures`}
        </button>
      )}
    </section>
  );
}

function range(values: string[]): string {
  if (!values.length) return "none";
  return values.length === 1 ? values[0] : `${values[0]}–${values[values.length - 1]}`;
}

export function Overview() {
  const [data, setData] = useState<{ player: Player; coverage: Coverage; comparison: Comparison } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.player(), api.coverage(), api.compare("silver")])
      .then(([player, coverage, comparison]) => setData({ player, coverage, comparison }))
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) {
    return (
      <Layout active="overview">
        <p className="mt-16 text-ink2">{error}</p>
      </Layout>
    );
  }
  if (!data) {
    return (
      <Layout active="overview">
        <p className="mt-16 font-mono text-[12px] text-ink3">Loading your games…</p>
      </Layout>
    );
  }

  const { player, coverage, comparison } = data;
  const { themes, rows } = comparison;
  // Findings first, then the rest in a fixed order.
  const order = (t: Theme) => (t.status === "finding" ? 0 : t.status === "worth_watching" ? 1 : 2);
  const sorted = [...themes].sort((a, b) => order(a) - order(b));
  const winRate = rows.find((r) => r.value === "win_rate_pct");
  // Objective rows count objectives, not games, so they don't count here.
  const yourGames = Math.max(...rows.filter((r) => r.sample_unit === "games").map((r) => r.my_sample));

  return (
    <Layout active="overview">
      <ProfileHeader player={player} coverage={coverage} />

      <div className="pt-12">
        <h1 className="display max-w-[920px] text-[50px] leading-[1.02]">{headline(themes, WHO)}</h1>
        <p className="mt-5 max-w-[700px] text-[16px] text-ink2">
          Up to {yourGames} of your jungle games on patches {range(comparison.benchmark_patches)}, against{" "}
          {comparison.benchmark_games} games from {comparison.benchmark_players} {WHO} on the same patches. A
          difference only counts as clear when it's bigger than chance would explain. Hover any measure for its exact
          margin.
        </p>
      </div>

      {sorted.map((theme) => (
        <ThemeSection key={theme.theme} theme={theme} rows={rows} themes={themes} />
      ))}

      {winRate && (
        <section className="mt-16">
          <SectionHead
            label="Results"
            heading={stateOf(winRate, themes) === "unclear" ? "No clear difference in win rate" : "Win rate"}
            note="Win rate depends on four teammates as well, so it takes many games to settle."
            state={stateOf(winRate, themes)}
          />
          <div className="mt-6 grid gap-x-10 md:grid-cols-2 xl:grid-cols-3">
            <MeasureCard row={winRate} state={stateOf(winRate, themes)} cohort={COHORT} />
          </div>
        </section>
      )}

      <section className="mt-20 grid gap-6 border-t border-rule pt-6 text-[14px] text-ink2 md:grid-cols-[200px_1fr]">
        <div className="smallcaps text-ink3">What this covers</div>
        <div className="max-w-[720px] space-y-2">
          <p>
            {coverage.player.games} ranked games, {coverage.player.jungle_games} of them in the jungle, on patches{" "}
            {range(coverage.player.patches)}. Remakes are left out everywhere.
          </p>
          <p>
            Comparisons use only your jungle games on the benchmark's patches, so a measure can rest on fewer games than
            your total. Anything on fewer than 10 of your games says "Too early to tell".
          </p>
        </div>
      </section>
    </Layout>
  );
}
