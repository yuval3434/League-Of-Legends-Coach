// One pool champion, opened from the Draft page: the player's stats on it next
// to their overall average in the role, each rank's benchmark on it, and Riot's own
// text about it. Side by side, never subtracted: the champion's games are part
// of the overall average.

import { useEffect, useState } from "react";

import { api, type ChampionCard, type Role } from "../api";
import { benchmarkLines, sideCell } from "../card";
import { gameDate } from "../matches";
import { roleWord } from "../offers";

export function ChampionCardView({
  champion,
  player,
  name,
  role,
}: {
  champion: string;
  player: string | null;
  name: (id: string) => string;
  role: Role;
}) {
  const [card, setCard] = useState<ChampionCard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setCard(null);
    setError(null);
    api.championCard(champion, player, role).then(setCard).catch((e: Error) => setError(e.message));
  }, [champion, player, role]);

  if (error) return <p className="py-3 text-[14px] text-ink2">{error}</p>;
  if (!card) return <p className="py-3 font-mono text-[12px] text-ink3">Loading {name(champion)}…</p>;

  const display = name(champion);
  return (
    <div className="rounded-[3px] border border-rule bg-panel/40 px-4 py-4 sm:px-5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
        <div>
          <span className="text-[16px] text-ink">{display}</span>
          {card.riot && <span className="ml-2 text-[13px] text-ink3">{card.riot.title}</span>}
        </div>
        <span className="font-mono text-[11px] text-ink3">
          {card.games} {roleWord(card.role)} games{card.last_played ? ` · last played ${gameDate(card.last_played)}` : ""}
        </span>
      </div>

      <div className="relative mt-4 overflow-x-auto">
        <table className="w-full min-w-[480px] border-collapse text-[14px]">
          <thead>
            <tr>
              {["", `On ${display}`, `All ${roleWord(card.role)} games`].map((h) => (
                <th key={h || "stat"} scope="col" className="smallcaps border-b border-rule pb-2 pr-5 text-left font-normal text-ink3">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {card.rows.map((row) => {
              const mine = sideCell(row.stat, row.champion);
              const all = sideCell(row.stat, row.overall);
              return (
                <tr key={row.stat} className="border-b border-rule/60 align-top">
                  <th scope="row" className="py-2 pr-5 text-left font-normal text-ink2">
                    {row.label}
                  </th>
                  {[mine, all].map((cell, i) => (
                    <td key={i} className="py-2 pr-5">
                      <div className={`font-mono ${cell.low ? "text-ink3" : "text-ink"}`}>{cell.main}</div>
                      <div className="font-mono text-[11px] text-ink3">{cell.detail}</div>
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[12px] text-ink3">{card.notes[0]}</p>

      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        {Object.entries(card.benchmarks).map(([key, benchmark]) => {
          const rank = benchmark.tier.charAt(0) + benchmark.tier.slice(1).toLowerCase();
          const lines = benchmarkLines(benchmark, rank, display);
          return (
            <div key={key} className="border-t border-rule pt-2">
              <div className="smallcaps text-ink3">Benchmark: {rank}</div>
              <div className="mt-1 text-[14px] text-ink">{lines.main}</div>
              {lines.details.map((line) => (
                <div key={line} className="text-[13px] text-ink2">
                  {line}
                </div>
              ))}
            </div>
          );
        })}
      </div>

      {card.riot && (
        <div className="mt-5 border-t border-rule pt-3">
          <div className="smallcaps text-ink3">Riot's text, not from your games</div>
          {card.riot.ally_tips.length > 0 && (
            <>
              <div className="mt-2 text-[14px] text-ink">Riot's tips for playing {display}</div>
              <ul className="mt-1 list-disc space-y-1 pl-5 text-[13px] text-ink2">
                {card.riot.ally_tips.map((tip) => (
                  <li key={tip}>{tip}</li>
                ))}
              </ul>
            </>
          )}
          <details className="mt-3 text-[13px]">
            <summary className="cursor-pointer text-ink2 hover:text-ink">Abilities</summary>
            <dl className="mt-2 space-y-2">
              {card.riot.abilities.map((a) => (
                <div key={a.key}>
                  <dt className="text-ink">
                    <span className="font-mono text-[11px] text-ink3">{a.key}</span> {a.name}
                  </dt>
                  <dd className="whitespace-pre-line text-ink2">{a.description}</dd>
                </div>
              ))}
            </dl>
          </details>
          <p className="mt-2 text-[12px] text-ink3">{card.notes[1]}</p>
        </div>
      )}
    </div>
  );
}
