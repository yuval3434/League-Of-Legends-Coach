// A player against each cohort that could fit them in one role: their peers,
// and for junglers below Emerald a target. Gold and CS by minute as lines with
// the player's margin shaded, then every theme's verdict against each. A cohort
// that doesn't fit the player says "No benchmark" and why; nothing takes its place.

import { useEffect, useState } from "react";

import { api, type Comparison, type Offers, type Role, type Stretches, type Theme } from "../api";
import { Layout } from "../components/Layout";
import { MinuteChart, SeriesKey, seriesFor } from "../components/MinuteChart";
import { RoleTabs } from "../components/PullOffer";
import { StretchTable } from "../components/StretchTable";
import { Marker, type State } from "../components/Verdict";
import { type Compared, compareHeadline, MINUTES, minutePoints, minuteRow } from "../compare";
import { gapWords, THEME_NAMES } from "../metrics";
import { groupName, roleWord } from "../offers";
import { usePlayer } from "../player";
import { askCoach } from "../router";
import { themeState } from "../state";
import { type Subject, subjectOf, whoIs, whoLower, Whose, whose } from "../subject";
import { PLAIN, PLAIN_TONE } from "../verdict";

const VERDICT: Partial<Record<Theme["status"], string>> = {
  no_margin: "No verdict yet",
  context_only: "Context only",
  not_comparable: "Not compared",
  no_benchmark: "No benchmark",
};

function ok(c: Comparison): boolean {
  return c.status === "ok";
}

function rank(tier: string): string {
  return tier.charAt(0) + tier.slice(1).toLowerCase();
}

function ThemeVerdict({ comparison, theme }: { comparison: Comparison; theme: string }) {
  if (!ok(comparison)) return <span className="text-ink3">No benchmark</span>;
  const found = comparison.themes.find((t) => t.theme === theme);
  if (!found) return <span className="text-ink3">—</span>;
  const state: State = themeState(found);
  const label = VERDICT[found.status];
  // "Not compared" and "No verdict yet" aren't a verdict, so they get no marker.
  return (
    <span className={`inline-flex items-center gap-2 ${label ? "text-ink3" : PLAIN_TONE[state]}`}>
      {!label && <Marker state={state} size={8} />}
      {label ?? PLAIN[state]}
    </span>
  );
}

function AskLink({ question, children }: { question: string; children: string }) {
  return (
    <a
      href={askCoach(question)}
      className="text-[14px] text-ink2 underline decoration-rule underline-offset-4 hover:text-ink hover:decoration-ink3"
    >
      {children}
    </a>
  );
}

/** The chart lines' names: each cohort that has a benchmark for this player. */
function lineNames(cohorts: Compared[]): { peers?: string; target?: string } {
  const named = (slot: Compared["slot"]) => {
    const c = cohorts.find((x) => x.slot === slot);
    return c && ok(c.comparison) ? c.short : undefined;
  };
  return { peers: named("peers"), target: named("target") };
}

function ChartPanel({
  title,
  value,
  cohorts,
  subject,
}: {
  title: string;
  value: string;
  cohorts: Compared[];
  subject: Subject;
}) {
  const peers = cohorts.find((c) => c.slot === "peers");
  const target = cohorts.find((c) => c.slot === "target");
  const points = minutePoints(value, peers?.comparison ?? null, target?.comparison ?? null);
  const series = seriesFor(subject, lineNames(cohorts));
  const lastMinute = MINUTES[MINUTES.length - 1];
  const gaps = cohorts
    .filter((c) => ok(c.comparison))
    .map((c) => ({ name: c.short, row: minuteRow(c.comparison, value, lastMinute) }))
    .filter((g): g is { name: string; row: NonNullable<ReturnType<typeof minuteRow>> } => !!g.row);
  return (
    <div className="border-t border-rule pt-4">
      <h3 className="text-[16px] text-ink">{title}</h3>
      <div className="mt-3">
        <MinuteChart points={points} unitLabel={title} series={series} subject={subject} />
      </div>
      {gaps.length > 0 && (
        <p className="mt-2 text-[14px] text-ink3">
          At {lastMinute} min {subject.you ? "you're" : whoIs(subject)}{" "}
          {gaps.map((g, i) => (
            <span key={g.name}>
              {i > 0 && " and "}
              <span className="text-ink2">{gapWords(g.row, g.name)}</span>
            </span>
          ))}
          , on {gaps[0].row.my_sample} of {whose(subject)} games.
        </p>
      )}
    </div>
  );
}

/** Each comparison's notes: one every cohort carries is shown once, without a cohort. */
function noteList(compared: Compared[]): { cohort: string; note: string }[] {
  const shared = (note: string) => compared.every((c) => c.comparison.notes.includes(note));
  const first = compared[0]?.comparison.notes.filter(shared).map((note) => ({ cohort: "", note })) ?? [];
  const own = compared.flatMap((c) =>
    c.comparison.notes.filter((note) => !shared(note)).map((note) => ({ cohort: c.short, note })),
  );
  return [...first, ...own];
}

export function Compare() {
  const { puuid, player, error: playerError } = usePlayer();
  const [offers, setOffers] = useState<Offers | null>(null);
  const [role, setRole] = useState<Role | null>(null);
  const [compared, setCompared] = useState<Compared[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Loaded on its own, so the rest of the page doesn't wait for it or fail with it.
  const [stretches, setStretches] = useState<Stretches | null>(null);

  useEffect(() => {
    // Another player's comparisons must never show under this one's name.
    setOffers(null);
    setCompared(null);
    setStretches(null);
    setRole(null);
    setError(null);
    api.offers(puuid).then(setOffers).catch((e: Error) => setError(e.message));
  }, [puuid]);

  const roles = offers?.roles ?? [];
  const offer = roles.find((r) => r.role === role) ?? roles[0] ?? null;

  useEffect(() => {
    if (!offers) return;
    setCompared(null);
    setStretches(null);
    if (!offer) {
      setCompared([]);
      return;
    }
    Promise.all(offer.cohorts.map((c) => api.compare(c.cohort, puuid)))
      .then((comparisons) =>
        setCompared(
          offer.cohorts.map((c, i) => ({
            slot: c.audience === "peers" ? "peers" : "target",
            short: rank(c.tier),
            group: groupName(c.tier, c.role),
            comparison: comparisons[i],
          })),
        ),
      )
      .catch((e: Error) => setError(e.message));
    api
      .stretches(puuid, offer.role)
      .then(setStretches)
      .catch(() => setStretches(null));
  }, [offers, offer, puuid]);

  const failed = playerError ?? error;
  if (failed || !compared || !player) {
    return (
      <Layout active="compare">
        <p className={`mt-16 ${failed ? "text-ink2" : "font-mono text-[12px] text-ink3"}`}>
          {failed ?? "Loading the comparisons…"}
        </p>
      </Layout>
    );
  }

  const s = subjectOf(player);
  const usable = compared.filter((c) => ok(c.comparison));
  const themes = (usable[0] ?? compared[0])?.comparison.themes.map((t) => t.theme) ?? [];
  const peers = compared.find((c) => c.slot === "peers");
  const target = compared.find((c) => c.slot === "target");
  const notes = noteList(compared);
  const sizes = usable.map(
    (c) => `${c.comparison.benchmark_games} games from ${c.comparison.benchmark_players} ${c.group}`,
  );
  const games = offer ? `${roleWord(offer.role)} games` : "games";
  const opponent = offer?.role === "JUNGLE" ? "the enemy jungler" : "the lane opponent";
  const me = s.you ? "I" : s.name;
  const does = s.you ? "do I" : `does ${s.name}`;
  const askAbout = target && ok(target.comparison) ? target : peers;

  return (
    <Layout active="compare">
      <div className="pt-12">
        <div className="smallcaps text-ink3">Compare</div>
        <h1 className="display mt-1.5 max-w-[960px] text-[50px] leading-[1.02]">{compareHeadline(compared, s)}</h1>
        <p className="mt-5 max-w-[720px] text-[16px] text-ink2">
          {usable.length > 0
            ? `${Whose(s)} ${games} against ${sizes.join(" and ")}, all on the same patches.` +
              (target && peers ? ` ${peers.short} is ${whose(s)} own rank; ${target.short} is a target, a rank above.` : "")
            : `No benchmark fits ${whoLower(s)}${offer ? ` in ${roleWord(offer.role)}` : ""}, so nothing is compared. The notes below say why.`}
        </p>
        {offer && <RoleTabs roles={roles.map((r) => r.role)} role={offer.role} onChange={setRole} />}
      </div>

      {usable.length > 0 && (
        <section className="mt-14">
          <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-3">
            <div>
              <div className="smallcaps text-ink3">Farm and gold</div>
              <h2 className="display mt-1.5 text-[30px] leading-[1.1]">Minute by minute</h2>
            </div>
            <SeriesKey series={seriesFor(s, lineNames(compared))} subject={s} />
          </div>
          <div className="mt-6 grid gap-x-12 gap-y-10 lg:grid-cols-2">
            <ChartPanel title="Gold" value="avg_gold" cohorts={compared} subject={s} />
            <ChartPanel title="CS, lane minions and jungle camps" value="avg_cs" cohorts={compared} subject={s} />
          </div>
          <p className="mt-4 text-[13px] text-ink3">Hover a minute for the exact numbers.</p>
          <div className="mt-5">
            <AskLink question={`Where in the game ${does} fall behind on farm, and what should ${me} change?`}>
              {s.you ? "Ask the coach where you lose farm" : `Ask the coach where ${s.name} loses farm`}
            </AskLink>
          </div>
        </section>
      )}

      {stretches && (
        <section className="mt-16">
          <div className="smallcaps text-ink3">Stretch by stretch</div>
          <h2 className="display mt-1.5 text-[30px] leading-[1.1]">Where farm is lost</h2>
          <p className="mt-3 max-w-[720px] text-[15px] text-ink2">
            What {s.you ? "you gain" : `${s.name} gains`} in each stretch of the game, against {opponent} in the same
            games, and against what each rank gains in the same stretch.
          </p>
          <div className="mt-6">
            <StretchTable data={stretches} />
          </div>
          <ul className="mt-4 max-w-[760px] space-y-1.5 text-[13px] text-ink3">
            {stretches.notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
          <div className="mt-5">
            <AskLink question={`In which stretch of the game ${does} lose the most farm to ${opponent}?`}>
              {s.you ? "Ask the coach when you lose farm" : `Ask the coach when ${s.name} loses farm`}
            </AskLink>
          </div>
        </section>
      )}

      {compared.length > 0 && (
        <section className="mt-16">
          <div className="smallcaps text-ink3">Theme by theme</div>
          <h2 className="display mt-1.5 text-[30px] leading-[1.1]">Against each rank</h2>
          <table className="mt-6 w-full max-w-[760px] border-collapse text-[14px]">
            <thead>
              <tr>
                <th scope="col" className="smallcaps border-b border-rule pb-2 text-left font-normal text-ink3">
                  Theme
                </th>
                {compared.map((c) => (
                  <th key={c.short} scope="col" className="smallcaps border-b border-rule pb-2 text-left font-normal text-ink3">
                    Against {c.short}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {themes.map((name) => (
                <tr key={name} className="border-b border-rule/60">
                  <th scope="row" className="py-3 pr-6 text-left font-normal text-ink">
                    {THEME_NAMES[name] ?? name}
                  </th>
                  {compared.map((c) => (
                    <td key={c.short} className="py-3 pr-6">
                      <ThemeVerdict comparison={c.comparison} theme={name} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {notes.length > 0 && (
            <ul className="mt-5 max-w-[760px] space-y-1.5 text-[13px] text-ink3">
              {notes.map(({ cohort, note }) => (
                <li key={`${cohort}${note}`}>
                  {cohort && <span className="text-ink2">{cohort}:</span>} {note}
                </li>
              ))}
            </ul>
          )}
          {usable.length > 0 && askAbout && (
            <div className="mt-6">
              <AskLink
                question={`What's the biggest difference between ${s.you ? "me" : s.name} and ${askAbout.group}, and what should ${me} work on first?`}
              >
                {`Ask the coach what ${s.you ? "to work on" : `${s.name} should work on`} first`}
              </AskLink>
            </div>
          )}
        </section>
      )}
    </Layout>
  );
}
