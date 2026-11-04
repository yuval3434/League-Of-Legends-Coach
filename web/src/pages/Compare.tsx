// A player against two cohorts at once: Silver (peers) and Emerald (a target).
// Gold and CS by minute as lines with the player's margin shaded, then every
// theme's verdict against both. A cohort that doesn't fit the player says
// "No benchmark" and why; nothing takes its place.

import { useEffect, useState } from "react";

import { api, type Comparison, type Stretches, type Theme } from "../api";
import { Layout } from "../components/Layout";
import { MinuteChart, SeriesKey, seriesFor } from "../components/MinuteChart";
import { StretchTable } from "../components/StretchTable";
import { Marker, type State } from "../components/Verdict";
import { compareHeadline, MINUTES, minutePoints, minuteRow } from "../compare";
import { gapWords, THEME_NAMES } from "../metrics";
import { usePlayer } from "../player";
import { askCoach } from "../router";
import { themeState } from "../state";
import { type Subject, subjectOf, whoIs, whoLower, Whose, whose } from "../subject";
import { PLAIN, PLAIN_TONE } from "../verdict";

const VERDICT: Partial<Record<Theme["status"], string>> = {
  no_margin: "No verdict yet",
  not_comparable: "Not compared",
  no_benchmark: "No benchmark",
};

const COHORTS = [
  { key: "silver", name: "Silver" },
  { key: "emerald", name: "Emerald" },
] as const;

function ok(c: Comparison): boolean {
  return c.status === "ok";
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

function ChartPanel({
  title,
  value,
  silver,
  emerald,
  subject,
}: {
  title: string;
  value: string;
  silver: Comparison;
  emerald: Comparison;
  subject: Subject;
}) {
  const points = minutePoints(value, silver, emerald);
  const series = seriesFor(subject, { silver: ok(silver), emerald: ok(emerald) });
  const lastMinute = MINUTES[MINUTES.length - 1];
  const gaps = COHORTS.map(({ key, name }) => {
    const c = key === "silver" ? silver : emerald;
    return ok(c) ? { name, row: minuteRow(c, value, lastMinute) } : null;
  }).filter((g): g is { name: "Silver" | "Emerald"; row: NonNullable<ReturnType<typeof minuteRow>> } => !!g?.row);
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

export function Compare() {
  const { puuid, player, error: playerError } = usePlayer();
  const [data, setData] = useState<{ silver: Comparison; emerald: Comparison } | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Loaded on its own, so the rest of the page doesn't wait for it or fail with it.
  const [stretches, setStretches] = useState<Stretches | null>(null);

  useEffect(() => {
    setData(null);
    setError(null);
    setStretches(null);
    Promise.all([api.compare("silver", puuid), api.compare("emerald", puuid)])
      .then(([silver, emerald]) => setData({ silver, emerald }))
      .catch((e: Error) => setError(e.message));
    api
      .stretches(puuid)
      .then(setStretches)
      .catch(() => setStretches(null));
  }, [puuid]);

  const failed = playerError ?? error;
  if (failed || !data || !player) {
    return (
      <Layout active="compare">
        <p className={`mt-16 ${failed ? "text-ink2" : "font-mono text-[12px] text-ink3"}`}>
          {failed ?? "Loading the comparisons…"}
        </p>
      </Layout>
    );
  }

  const s = subjectOf(player);
  const { silver, emerald } = data;
  const usable = [silver, emerald].filter(ok);
  const themes = (usable[0] ?? silver).themes.map((t) => t.theme);
  // A note both comparisons carry is shown once, without a cohort.
  const notes = [
    ...silver.notes.filter((n) => emerald.notes.includes(n)).map((note) => ({ cohort: "", note })),
    ...silver.notes.filter((n) => !emerald.notes.includes(n)).map((note) => ({ cohort: "Silver", note })),
    ...emerald.notes.filter((n) => !silver.notes.includes(n)).map((note) => ({ cohort: "Emerald", note })),
  ];
  const sizes = COHORTS.filter(({ key }) => ok(data[key])).map(
    ({ key, name }) => `${data[key].benchmark_games} games from ${data[key].benchmark_players} ${name} junglers`,
  );
  const me = s.you ? "I" : s.name;
  const does = s.you ? "do I" : `does ${s.name}`;

  return (
    <Layout active="compare">
      <div className="pt-12">
        <div className="smallcaps text-ink3">Compare</div>
        <h1 className="display mt-1.5 max-w-[960px] text-[50px] leading-[1.02]">{compareHeadline(silver, emerald, s)}</h1>
        <p className="mt-5 max-w-[720px] text-[16px] text-ink2">
          {usable.length > 0
            ? `${Whose(s)} jungle games against ${sizes.join(" and ")}, all on the same patches. Silver is for Silver players; Emerald is a target for anyone ranked below it.`
            : `No benchmark fits ${whoLower(s)}, so nothing is compared. The notes below say why.`}
        </p>
      </div>

      {usable.length > 0 && (
        <section className="mt-14">
          <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-3">
            <div>
              <div className="smallcaps text-ink3">Farm and gold</div>
              <h2 className="display mt-1.5 text-[30px] leading-[1.1]">Minute by minute</h2>
            </div>
            <SeriesKey series={seriesFor(s, { silver: ok(silver), emerald: ok(emerald) })} subject={s} />
          </div>
          <div className="mt-6 grid gap-x-12 gap-y-10 lg:grid-cols-2">
            <ChartPanel title="Gold" value="avg_gold" silver={silver} emerald={emerald} subject={s} />
            <ChartPanel title="CS, lane minions and jungle camps" value="avg_cs" silver={silver} emerald={emerald} subject={s} />
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
            What {s.you ? "you gain" : `${s.name} gains`} in each stretch of the game, against the enemy jungler in the
            same games, and against what each rank gains in the same stretch.
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
            <AskLink question={`In which stretch of the game ${does} lose the most farm to the enemy jungler?`}>
              {s.you ? "Ask the coach when you lose farm" : `Ask the coach when ${s.name} loses farm`}
            </AskLink>
          </div>
        </section>
      )}

      <section className="mt-16">
        <div className="smallcaps text-ink3">Theme by theme</div>
        <h2 className="display mt-1.5 text-[30px] leading-[1.1]">Against each rank</h2>
        <table className="mt-6 w-full max-w-[760px] border-collapse text-[14px]">
          <thead>
            <tr>
              <th scope="col" className="smallcaps border-b border-rule pb-2 text-left font-normal text-ink3">
                Theme
              </th>
              {COHORTS.map(({ name }) => (
                <th key={name} scope="col" className="smallcaps border-b border-rule pb-2 text-left font-normal text-ink3">
                  Against {name}
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
                {COHORTS.map(({ key }) => (
                  <td key={key} className="py-3 pr-6">
                    <ThemeVerdict comparison={data[key]} theme={name} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {notes.length > 0 && (
          <ul className="mt-5 max-w-[760px] space-y-1.5 text-[13px] text-ink3">
            {notes.map(({ cohort, note }) => (
              <li key={note}>
                {cohort && <span className="text-ink2">{cohort}:</span>} {note}
              </li>
            ))}
          </ul>
        )}
        {usable.length > 0 && (
          <div className="mt-6">
            <AskLink
              question={`What's the biggest difference between ${s.you ? "me" : s.name} and ${
                ok(emerald) ? "Emerald" : "Silver"
              } junglers, and what should ${me} work on first?`}
            >
              {`Ask the coach what ${s.you ? "to work on" : `${s.name} should work on`} first`}
            </AskLink>
          </div>
        )}
      </section>
    </Layout>
  );
}
