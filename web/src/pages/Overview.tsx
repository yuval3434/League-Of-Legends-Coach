import { useEffect, useState } from "react";

import {
  api,
  type CohortOffer,
  type CompareRow,
  type Comparison,
  type Coverage,
  type Offers,
  type OwnNumbers,
  type PullStatus,
  type Role,
  type RoleOffer,
  type Theme,
} from "../api";
import { Layout } from "../components/Layout";
import { MeasureCard } from "../components/MeasureCard";
import { ProfileHeader } from "../components/ProfileHeader";
import { OwnNumbersView } from "../components/OwnNumbersView";
import { PullOffer, RoleTabs } from "../components/PullOffer";
import { Marker, type State } from "../components/Verdict";
import { headline } from "../headline";
import { fmt, metricLabel } from "../metrics";
import { comparedWith, groupName, peers, roleWord } from "../offers";
import { usePlayer } from "../player";
import { href } from "../router";
import { stateOf, themeState } from "../state";
import { subjectOf, type Subject, verb, who, whoLower, whose, Whose } from "../subject";
import { PLAIN, PLAIN_TONE } from "../verdict";

/** Who the page is about, whom they're measured against, and in which role. */
type Words = { cohort: string; group: string; s: Subject; role: Role };

type Key = { value: string; minute?: number; phase?: string };

const TOPICS: Record<string, string> = {
  economy: "farm",
  vision: "vision",
  deaths: "deaths",
  fights: "fights",
  objectives: "objectives",
};

/** A theme's name in a sentence. A jungler's fights are only kill participation. */
function topicOf(theme: string, role: Role): string {
  if (theme === "fights" && role === "JUNGLE") return "kill participation";
  if (theme === "objectives" && role !== "JUNGLE") return "plates";
  return TOPICS[theme] ?? theme;
}

// The few measures that tell a theme's story; the rest wait behind "Show all".
const TELLING: Record<string, Key[]> = {
  economy: [{ value: "avg_cs_per_min" }, { value: "avg_cs", minute: 15 }, { value: "avg_gold", minute: 15 }],
  vision: [
    { value: "avg_placed_per_min" },
    { value: "avg_control_placed_per_min" },
    { value: "avg_destroyed_per_min" },
  ],
  deaths: [
    { value: "avg_deaths", phase: "early" },
    { value: "avg_deaths", phase: "mid" },
    { value: "avg_deaths", phase: "late" },
  ],
  fights: [
    { value: "avg_kill_participation_pct" },
    { value: "avg_solo_kills" },
    { value: "avg_damage_share_pct" },
    { value: "avg_roam_takedowns" },
  ],
  objectives: [{ value: "avg_lane_plates" }],
};

// What each fights measure says, for a finding's headline.
const FIGHTS: Record<string, (behind: boolean, s: Subject) => string> = {
  avg_kill_participation_pct: (behind, s) =>
    `${verb(s, "take")} part in ${behind ? "fewer" : "more"} of ${s.you ? "your" : "their"} team's kills`,
  avg_solo_kills: (behind, s) => `${verb(s, "get")} ${behind ? "fewer" : "more"} solo kills`,
  avg_solo_kills_before_15: (behind, s) => `${verb(s, "get")} ${behind ? "fewer" : "more"} solo kills`,
  avg_damage_share_pct: (behind, s) =>
    `${verb(s, "deal")} a ${behind ? "smaller" : "bigger"} share of ${s.you ? "your" : "their"} team's damage`,
};

/** "You farm less than" / "Ana farms more than", for a theme's finding. */
function lead(theme: string, behind: boolean, s: Subject, values: string[] = []): string | null {
  if (theme === "fights") {
    const parts = [...new Set(values.map((v) => FIGHTS[v]?.(behind, s)).filter((p): p is string => !!p))];
    if (parts.length) return `${who(s)} ${parts.join(" and ")} than`;
  }
  if (theme === "objectives" && values.every((v) => v === "avg_lane_plates")) {
    return `${who(s)} ${verb(s, "take")} ${behind ? "fewer" : "more"} plates in ${s.you ? "your" : "their"} lane than`;
  }
  switch (theme) {
    case "economy":
      return `${who(s)} ${verb(s, "farm")} ${behind ? "less" : "more"} than`;
    case "deaths":
      return `${who(s)} ${verb(s, "die")} ${behind ? "more" : "less"} than`;
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
  const topic = topicOf(theme.theme, w.role);
  if (theme.status === "finding") {
    const finding = theme.findings?.find((f) => f.direction === "behind") ?? theme.findings![0];
    if (theme.theme === "vision") {
      const control = finding.rows.some((r) => r.value === "avg_control_placed_per_min");
      const destroyed = finding.rows.some((r) => r.value === "avg_destroyed_per_min");
      const more = finding.direction === "ahead" ? "more" : "fewer";
      if (!control && !destroyed) return `${who(w.s)} ${verb(w.s, "place")} ${more} wards than ${w.group}`;
      const place = `${who(w.s)} ${verb(w.s, "place")} ${more} control wards`;
      if (control && destroyed) return `${place} and ${verb(w.s, "destroy")} ${more} wards than ${w.group}`;
      return control ? `${place} than ${w.group}` : `${who(w.s)} ${verb(w.s, "destroy")} ${more} wards than ${w.group}`;
    }
    const words = lead(
      theme.theme,
      finding.direction === "behind",
      w.s,
      finding.rows.map((r) => r.value),
    );
    return words ? `${words} ${w.group}` : capital(topic);
  }
  switch (theme.status) {
    case "worth_watching":
      return `Might be a gap in ${topic}`;
    case "nothing_clear":
      return `No clear difference in ${topic}`;
    case "no_margin":
      return `${capital(topic)} can't be judged yet`;
    case "context_only":
      return `${capital(topic)}: context, not judged`;
    case "not_enough_data":
      return `Too early to tell on ${topic}`;
    case "no_benchmark":
      return `No benchmark for ${topic}`;
    default:
      return `${capital(topic)} isn't compared with this cohort`;
  }
}

function explanation(theme: Theme, w: Words): string {
  const topic = topicOf(theme.theme, w.role);
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
    case "context_only":
      return `For ${w.group}, these are shown beside the benchmark but never judged.`;
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
            player who swaps to Oracle Lens places few trinket wards, so this shows trinket choice, not vision.
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
  const topic = topicOf(theme.theme, w.role);
  const objectives = theme.theme === "objectives" ? rows.filter((r) => r.theme === "objectives" && r.value === "team_share_pct") : [];

  return (
    <section className="mt-16">
      <SectionHead
        label={capital(topic)}
        heading={title(theme, w)}
        note={explanation(theme, w)}
        state={themeState(theme)}
        verdict={
          theme.status === "no_margin" ? "No verdict yet" : theme.status === "context_only" ? "Context only" : undefined
        }
      />
      {shown.length > 0 && (
        <div className="mt-6 grid gap-x-10 gap-y-2 md:grid-cols-2 xl:grid-cols-3">
          {shown.map((row) => (
            <MeasureCard
              key={metricLabel(row, w.role)}
              row={row}
              state={stateOf(row, themes)}
              cohort={w.cohort}
              subject={w.s}
              role={w.role}
            />
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

/** Why a cohort gives no comparison: it doesn't fit, or it's too small so far. */
function reasonFor(c: CohortOffer): string {
  if (c.why_not) return c.why_not;
  const group = groupName(c.tier, c.role);
  if (!c.games) return `No benchmark of ${group} has been pulled yet.`;
  return `The benchmark of ${group} has ${c.games} games from ${c.players} players so far; it needs 30 games from 10 players.`;
}

/** No cohort fits this player in this role: say why, in the server's words, and never show another's. */
function NoBenchmark({ offer, s }: { offer: RoleOffer | null; s: Subject }) {
  const reasons = offer
    ? [...new Set(offer.cohorts.map(reasonFor))]
    : ["This player has no ranked games, so there's nothing to compare."];
  return (
    <div className="pt-12">
      <h1 className="display max-w-[920px] text-[50px] leading-[1.02]">
        No benchmark fits {whoLower(s)}
        {offer ? ` in ${roleWord(offer.role)}` : ""} yet
      </h1>
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

// How often a running pull's progress is checked.
const PULL_POLL_MS = 15_000;

export function Overview() {
  const { puuid, player, error: playerError } = usePlayer();
  const [base, setBase] = useState<{ coverage: Coverage; offers: Offers } | null>(null);
  const [role, setRole] = useState<Role | null>(null);
  // undefined while loading; null when no cohort can be compared with.
  const [comparison, setComparison] = useState<Comparison | null | undefined>(undefined);
  const [status, setStatus] = useState<PullStatus>({ state: "idle" });
  const [own, setOwn] = useState<OwnNumbers | null>(null);
  const [pullError, setPullError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (!player) return;
    setError(null);
    Promise.all([api.coverage(puuid), api.offers(puuid)])
      .then(([coverage, offers]) => {
        setBase({ coverage, offers });
        setStatus(offers.pull);
      })
      .catch((e: Error) => setError(e.message));
  }, [player, puuid, reload]);

  const roles = base?.offers.roles ?? [];
  const offer = roles.find((r) => r.role === role) ?? roles[0] ?? null;
  const cohort = offer ? comparedWith(offer)?.cohort ?? null : null;

  useEffect(() => {
    if (!base) return;
    setComparison(undefined);
    if (!cohort) {
      setComparison(null);
      return;
    }
    api.compare(cohort, puuid).then(setComparison).catch((e: Error) => setError(e.message));
  }, [base, cohort, puuid]);

  // With no benchmark, the player's own numbers in the role take the page.
  const noBenchmark = comparison === null || comparison?.status === "no_benchmark";
  const ownRole = noBenchmark && offer ? offer.role : null;
  useEffect(() => {
    setOwn(null);
    if (!ownRole) return;
    api.own(ownRole, puuid).then(setOwn).catch((e: Error) => setError(e.message));
  }, [ownRole, puuid]);

  // While a pull runs, check on it; when it ends, reload what can be compared.
  useEffect(() => {
    if (status.state !== "running") return;
    const timer = setInterval(() => {
      api
        .pullStatus()
        .then((next) => {
          setStatus(next);
          if (next.state !== "running") setReload((n) => n + 1);
        })
        .catch(() => undefined);
    }, PULL_POLL_MS);
    return () => clearInterval(timer);
  }, [status.state]);

  const startPull = (c: CohortOffer, more: boolean) => {
    setPullError(null);
    api.pull(c.cohort, puuid, more).then(setStatus).catch((e: Error) => setPullError(e.message));
  };
  const peer = offer ? peers(offer) : null;
  const pullOffer = peer && !peer.why_not && (
    <PullOffer offer={peer} status={status} error={pullError} onStart={(more) => startPull(peer, more)} />
  );
  const tabs = offer && <RoleTabs roles={roles.map((r) => r.role)} role={offer.role} onChange={setRole} />;

  const failed = playerError ?? error;
  if (failed) {
    return (
      <Layout active="overview">
        <p className="mt-16 text-ink2">{failed}</p>
      </Layout>
    );
  }
  if (!player || !base || comparison === undefined) {
    return (
      <Layout active="overview">
        <p className="mt-16 font-mono text-[12px] text-ink3">Loading games…</p>
      </Layout>
    );
  }

  const s = subjectOf(player);
  const { coverage } = base;
  if (!comparison || comparison.status !== "ok") {
    return (
      <Layout active="overview">
        <ProfileHeader player={player} coverage={coverage} />
        {tabs}
        <NoBenchmark offer={offer} s={s} />
        {pullOffer}
        {own && own.role === offer?.role && <OwnNumbersView data={own} s={s} />}
      </Layout>
    );
  }

  const name = comparison.tier.charAt(0) + comparison.tier.slice(1).toLowerCase();
  const games = `${roleWord(comparison.role)} games`;
  const w: Words = { cohort: name, group: groupName(comparison.tier, comparison.role), s, role: comparison.role };
  const { themes, rows } = comparison;
  // Findings first, then the rest in a fixed order.
  const order = (t: Theme) => (t.status === "finding" ? 0 : t.status === "worth_watching" ? 1 : 2);
  // A theme this role doesn't measure at all is left out; one a target cohort
  // doesn't compare still says so.
  const measured = themes.filter((t) => t.status !== "not_comparable" || (comparison.not_comparable ?? []).length > 0);
  const sorted = [...measured].sort((a, b) => order(a) - order(b));
  const winRate = rows.find((r) => r.value === "win_rate_pct");
  // Objective rows count objectives, not games, so they don't count here.
  const theirGames = Math.max(...rows.filter((r) => r.sample_unit === "games").map((r) => r.my_sample));
  const target = cohort === "emerald";

  return (
    <Layout active="overview">
      <ProfileHeader player={player} coverage={coverage} />
      {tabs}

      <div className="pt-12">
        <h1 className="display max-w-[920px] text-[50px] leading-[1.02]">{headline(themes, w.group, s)}</h1>
        <p className="mt-5 max-w-[700px] text-[16px] text-ink2">
          Up to {theirGames} of {whose(s)} {games} on patches {range(comparison.benchmark_patches)}, against{" "}
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
            {coverage.player.games} ranked games, {offer?.games ?? 0} of them {games}, on patches{" "}
            {range(coverage.player.patches)}. Remakes are left out everywhere.
          </p>
          <p>
            Comparisons use only {whose(s)} {games} on the benchmark's patches, so a measure can rest on fewer games
            than {whose(s)} total. Anything on fewer than 10 of {whose(s)} games says "Too early to tell".
          </p>
          {!s.you && (
            <p>
              The rank is {whose(s)} current solo/duo rank: Riot's match data doesn't say what rank each game was played
              at.
            </p>
          )}
          {pullOffer}
        </div>
      </section>
    </Layout>
  );
}
