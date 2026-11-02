// You against two cohorts at once: Silver (your rank) and Emerald (a target).
// Gold and CS by minute as lines with margin bands, then every theme's verdict
// against both, side by side.

import { useEffect, useState } from "react";

import { api, type Comparison, type Theme } from "../api";
import { Layout } from "../components/Layout";
import { MinuteChart, SeriesKey } from "../components/MinuteChart";
import { Marker, type State } from "../components/Verdict";
import { compareHeadline, MINUTES, minutePoints, minuteRow } from "../compare";
import { gapWords, THEME_NAMES } from "../metrics";
import { askCoach } from "../router";
import { themeState } from "../state";
import { PLAIN, PLAIN_TONE } from "../verdict";

const VERDICT: Partial<Record<Theme["status"], string>> = {
  no_margin: "No verdict yet",
  not_comparable: "Not compared",
  no_benchmark: "No benchmark",
};

function ThemeVerdict({ theme }: { theme: Theme | undefined }) {
  if (!theme) return <span className="text-ink3">—</span>;
  const state: State = themeState(theme);
  const label = VERDICT[theme.status];
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
}: {
  title: string;
  value: string;
  silver: Comparison;
  emerald: Comparison;
}) {
  const points = minutePoints(value, silver, emerald);
  const lastMinute = MINUTES[MINUTES.length - 1];
  const s = minuteRow(silver, value, lastMinute);
  const e = minuteRow(emerald, value, lastMinute);
  return (
    <div className="border-t border-rule pt-4">
      <h3 className="text-[16px] text-ink">{title}</h3>
      <div className="mt-3">
        <MinuteChart points={points} unitLabel={title} />
      </div>
      {s && e && (
        <p className="mt-2 text-[14px] text-ink3">
          At {lastMinute} min you're <span className="text-ink2">{gapWords(s, "Silver")}</span> and{" "}
          <span className="text-ink2">{gapWords(e, "Emerald")}</span>, on {s.my_sample} of your games.
        </p>
      )}
    </div>
  );
}

export function Compare() {
  const [data, setData] = useState<{ silver: Comparison; emerald: Comparison } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.compare("silver"), api.compare("emerald")])
      .then(([silver, emerald]) => setData({ silver, emerald }))
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error || !data) {
    return (
      <Layout active="compare">
        <p className={`mt-16 ${error ? "text-ink2" : "font-mono text-[12px] text-ink3"}`}>
          {error ?? "Loading the comparisons…"}
        </p>
      </Layout>
    );
  }

  const { silver, emerald } = data;
  const themes = silver.themes.map((t) => t.theme);
  const notes = [
    ...silver.notes.map((n) => ({ cohort: "Silver", note: n })),
    ...emerald.notes.map((n) => ({ cohort: "Emerald", note: n })),
  ];

  return (
    <Layout active="compare">
      <div className="pt-12">
        <div className="smallcaps text-ink3">Compare</div>
        <h1 className="display mt-1.5 max-w-[960px] text-[50px] leading-[1.02]">{compareHeadline(silver, emerald)}</h1>
        <p className="mt-5 max-w-[720px] text-[16px] text-ink2">
          Your jungle games against {silver.benchmark_games} games from {silver.benchmark_players} Silver junglers and{" "}
          {emerald.benchmark_games} from {emerald.benchmark_players} Emerald junglers, all on the same patches. Silver is
          your rank; Emerald shows where the next steps lead.
        </p>
      </div>

      <section className="mt-14">
        <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-3">
          <div>
            <div className="smallcaps text-ink3">Farm and gold</div>
            <h2 className="display mt-1.5 text-[30px] leading-[1.1]">Minute by minute</h2>
          </div>
          <SeriesKey />
        </div>
        <div className="mt-6 grid gap-x-12 gap-y-10 lg:grid-cols-2">
          <ChartPanel title="Gold" value="avg_gold" silver={silver} emerald={emerald} />
          <ChartPanel title="CS, lane minions and jungle camps" value="avg_cs" silver={silver} emerald={emerald} />
        </div>
        <p className="mt-4 text-[13px] text-ink3">Hover a minute for the exact numbers.</p>
        <div className="mt-5">
          <AskLink question="Where in the game do I fall behind Silver and Emerald junglers on farm, and what should I change?">
            Ask the coach where you lose farm
          </AskLink>
        </div>
      </section>

      <section className="mt-16">
        <div className="smallcaps text-ink3">Theme by theme</div>
        <h2 className="display mt-1.5 text-[30px] leading-[1.1]">Against each rank</h2>
        <table className="mt-6 w-full max-w-[760px] border-collapse text-[14px]">
          <thead>
            <tr>
              <th scope="col" className="smallcaps border-b border-rule pb-2 text-left font-normal text-ink3">
                Theme
              </th>
              <th scope="col" className="smallcaps border-b border-rule pb-2 text-left font-normal text-ink3">
                Against Silver
              </th>
              <th scope="col" className="smallcaps border-b border-rule pb-2 text-left font-normal text-ink3">
                Against Emerald
              </th>
            </tr>
          </thead>
          <tbody>
            {themes.map((name) => (
              <tr key={name} className="border-b border-rule/60">
                <th scope="row" className="py-3 pr-6 text-left font-normal text-ink">
                  {THEME_NAMES[name] ?? name}
                </th>
                <td className="py-3 pr-6">
                  <ThemeVerdict theme={silver.themes.find((t) => t.theme === name)} />
                </td>
                <td className="py-3">
                  <ThemeVerdict theme={emerald.themes.find((t) => t.theme === name)} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {notes.length > 0 && (
          <ul className="mt-5 max-w-[760px] space-y-1.5 text-[13px] text-ink3">
            {notes.map(({ cohort, note }) => (
              <li key={note}>
                <span className="text-ink2">{cohort}:</span> {note}
              </li>
            ))}
          </ul>
        )}
        <div className="mt-6">
          <AskLink question="What's the biggest difference between me and Emerald junglers, and what should I work on first?">
            Ask the coach what to work on first
          </AskLink>
        </div>
      </section>
    </Layout>
  );
}
