import { useEffect, useState } from "react";

import { api, type CompareRow, type Comparison, type Coverage, type Player, type Theme } from "../api";
import { Layout } from "../components/Layout";
import { MeasureCard } from "../components/MeasureCard";
import { ProfileHeader } from "../components/ProfileHeader";
import { Marker, type State } from "../components/Verdict";
import { headline } from "../headline";
import { fmt, metricLabel } from "../metrics";
import { mainCohort, usePlayer } from "../player";
import { href } from "../router";
import { stateOf, themeState } from "../state";
import { subjectOf, type Subject, verb, who, whoLower, whose, Whose } from "../subject";
import { PLAIN, PLAIN_TONE } from "../verdict";

/** Who the page is about, and whom they're measured against. */
type Words = { cohort: string; group: string; s: Subject };

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
  vision: [{ value: "avg_control_placed_per_min" }, { value: "avg_destroyed_per_min" }],
  deaths: [
    { value: "avg_deaths", phase: "early" },
    { value: "avg_deaths", phase: "mid" },
    { value: "avg_deaths", phase: "late" },
  ],
  fights: [{ value: "avg_kill_participation_pct" }],
};

/** "You farm less than" / "Ana farms more than", for a theme's finding. */
function lead(theme: string, behind: boolean, s: Subject): string | null {
  switch (theme) {
    case "economy":
      return `${who(s)} ${verb(s, "farm")} ${behind ? "less" : "more"} than`;
    case "deaths":
      return `${who(s)} ${verb(s, "die")} ${behind ? "more" : "less"} than`;
    case "fights":
      return `${who(s)} ${verb(s, "take")} part in ${behind ? "fewer" : "more"} of ${s.you ? "your" : "their"} team's kills than`;
    default:
      return null;
  }
}

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

function title(theme: Theme, w: Words): string {
  const topic = TOPIC[theme.theme] ?? theme.theme;
  if (theme.status === "finding") {
    const finding = theme.findings?.find((f) => f.direction === "behind") ?? theme.findings![0];
    if (theme.theme === "vision") {
      const control = finding.rows.some((r) => r.value === "avg_control_placed_per_min");
      const destroyed = finding.rows.some((r) => r.value === "avg_destroyed_per_min");
      const more = finding.direction === "ahead" ? "more" : "fewer";
      const place = `${who(w.s)} ${verb(w.s, "place")} ${more} control wards`;
      if (control && destroyed) return `${place} and ${verb(w.s, "destroy")} ${more} wards than ${w.group}`;
      return control ? `${place} than ${w.group}` : `${who(w.s)} ${verb(w.s, "destroy")} ${more} wards than ${w.group}`;
    }
    const words = lead(theme.theme, finding.direction === "behind", w.s);
    return words ? `${words} ${w.group}` : capital(topic);
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

function explanation(theme: Theme, w: Words): string {
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
      return `${Whose(w.s)} numbers and ${w.cohort}'s overlap, so any gap here could be chance.`;
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

/** Vision's background numbers: shown so the verdict can be read in context, never judged. */
function VisionContext({ rows, w }: { rows: CompareRow[]; w: Words }) {
  const get = (value: string) => rows.find((r) => r.value === value && r.context_only);
  const trinket = get("avg_trinket_placed_per_min");
  const lens = get("oracle_lens_pct");
  const score = get("avg_vision_score_per_min");
  if (!trinket && !lens && !score) return null;
  const pair = (r: CompareRow, suffix = "") => (
    <>
      {whoLower(w.s)} <span className="text-ink2">{fmt(r.my_value)}{suffix}</span> · {w.cohort} {fmt(r.benchmark_value)}
      {suffix}
    </>
  );
  return (
    <div className="mt-6 max-w-[860px] border-l border-rule pl-4 text-[14px] leading-relaxed text-ink3">
      <div className="smallcaps">Context, not judged</div>
      <ul className="mt-1.5 space-y-1">
        {trinket && (
          <li>
            Trinket wards placed per minute: {pair(trinket)}.
            {lens && <> Games ending with Oracle Lens: {pair(lens, "%")}, on {lens.my_sample} of {whose(w.s)} games.</>} A
            jungler who swaps to Oracle Lens places few trinket wards, so this shows trinket choice, not vision.
          </li>
        )}
        {score && (
          <li>
            Vision score per minute: {pair(score)}. Riot's formula for vision score isn't public, so it never gets a
            verdict here.
          </li>
        )}
      </ul>
    </div>
  );
}

function ThemeSection({ theme, rows, themes, w }: { theme: Theme; rows: CompareRow[]; themes: Theme[]; w: Words }) {
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
        heading={title(theme, w)}
        note={explanation(theme, w)}
        state={themeState(theme)}
        verdict={theme.status === "no_margin" ? "No verdict yet" : undefined}
      />
      {shown.length > 0 && (
        <div className="mt-6 grid gap-x-10 gap-y-2 md:grid-cols-2 xl:grid-cols-3">
          {shown.map((row) => (
            <MeasureCard key={metricLabel(row)} row={row} state={stateOf(row, themes)} cohort={w.cohort} subject={w.s} />
          ))}
        </div>
      )}
      {theme.theme === "vision" && <VisionContext rows={rows} w={w} />}
      {objectives.length > 0 && (
        <div className="mt-5 flex flex-wrap gap-x-10 gap-y-2 text-[14px] text-ink3">
          {objectives.map((r) => (
            <span key={r.objective}>
              {metricLabel(r)}: {whose(w.s)} team took {fmt(r.my_value)}% of {r.my_sample} · {w.cohort}{" "}
              {fmt(r.benchmark_value)}%
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

/** No cohort fits this player: say why, in the server's words, and never show another's. */
function NoBenchmark({ player, s }: { player: Player; s: Subject }) {
  const reasons = [...new Set(Object.values(player.benchmarks).filter((r): r is string => r !== null))];
  return (
    <div className="pt-12">
      <h1 className="display max-w-[920px] text-[50px] leading-[1.02]">No benchmark fits {whoLower(s)} yet</h1>
      <ul className="mt-5 max-w-[700px] space-y-1 text-[16px] text-ink2">
        {reasons.map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>
      <p className="mt-5 max-w-[700px] text-[16px] text-ink2">
        Nothing is compared with another rank or another player in its place.{" "}
        <a href={href("champions")} className="text-ink underline decoration-rule underline-offset-4 hover:decoration-ink3">
          {Whose(s)} champions
        </a>{" "}
        still show every game.
      </p>
    </div>
  );
}

export function Overview() {
  const { puuid, player, error: playerError } = usePlayer();
  const [data, setData] = useState<{ coverage: Coverage; comparison: Comparison | null } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const cohort = player ? mainCohort(player) : null;

  useEffect(() => {
    if (!player) return;
    setData(null);
    setError(null);
    Promise.all([api.coverage(puuid), cohort ? api.compare(cohort, puuid) : Promise.resolve(null)])
      .then(([coverage, comparison]) => setData({ coverage, comparison }))
      .catch((e: Error) => setError(e.message));
  }, [player, puuid, cohort]);

  const failed = playerError ?? error;
  if (failed) {
    return (
      <Layout active="overview">
        <p className="mt-16 text-ink2">{failed}</p>
      </Layout>
    );
  }
  if (!player || !data) {
    return (
      <Layout active="overview">
        <p className="mt-16 font-mono text-[12px] text-ink3">Loading games…</p>
      </Layout>
    );
  }

  const s = subjectOf(player);
  const { coverage, comparison } = data;
  if (!comparison || comparison.status !== "ok") {
    return (
      <Layout active="overview">
        <ProfileHeader player={player} coverage={coverage} />
        <NoBenchmark player={player} s={s} />
      </Layout>
    );
  }

  const name = comparison.tier.charAt(0) + comparison.tier.slice(1).toLowerCase();
  const w: Words = { cohort: name, group: `${name} junglers`, s };
  const { themes, rows } = comparison;
  // Findings first, then the rest in a fixed order.
  const order = (t: Theme) => (t.status === "finding" ? 0 : t.status === "worth_watching" ? 1 : 2);
  const sorted = [...themes].sort((a, b) => order(a) - order(b));
  const winRate = rows.find((r) => r.value === "win_rate_pct");
  // Objective rows count objectives, not games, so they don't count here.
  const theirGames = Math.max(...rows.filter((r) => r.sample_unit === "games").map((r) => r.my_sample));
  const target = cohort === "emerald";

  return (
    <Layout active="overview">
      <ProfileHeader player={player} coverage={coverage} />

      <div className="pt-12">
        <h1 className="display max-w-[920px] text-[50px] leading-[1.02]">{headline(themes, w.group, s)}</h1>
        <p className="mt-5 max-w-[700px] text-[16px] text-ink2">
          Up to {theirGames} of {whose(s)} jungle games on patches {range(comparison.benchmark_patches)}, against{" "}
          {comparison.benchmark_games} games from {comparison.benchmark_players} {w.group} on the same patches.
          {target && ` ${name} is a target, a rank above, not ${whose(s)} peers.`} A difference only counts as clear when
          it's bigger than chance would explain. Hover any measure for its exact margin.
        </p>
      </div>

      {sorted.map((theme) => (
        <ThemeSection key={theme.theme} theme={theme} rows={rows} themes={themes} w={w} />
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
            <MeasureCard row={winRate} state={stateOf(winRate, themes)} cohort={w.cohort} subject={s} />
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
            Comparisons use only {whose(s)} jungle games on the benchmark's patches, so a measure can rest on fewer games
            than {whose(s)} total. Anything on fewer than 10 of {whose(s)} games says "Too early to tell".
          </p>
          {!s.you && (
            <p>
              The rank is {whose(s)} current solo/duo rank: Riot's match data doesn't say what rank each game was played
              at.
            </p>
          )}
        </div>
      </section>
    </Layout>
  );
}
