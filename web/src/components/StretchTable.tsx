// Gold or CS by stretch of the game, against the lane opponent and each cohort.
// A cell with too few games says so instead of giving an amount, and a cohort
// that doesn't fit the player says "No benchmark". Never part of a finding.

import { useState } from "react";

import type { Stretches } from "../api";
import { cohortCell, type Cell, opponentCell, STRETCHES, type Tone, type Unit } from "../stretches";

const TONE: Record<Tone, string> = { clear: "text-ink", unclear: "text-ink2", low: "text-ink3" };

function rank(tier: string): string {
  return tier.charAt(0) + tier.slice(1).toLowerCase();
}

function CellView({ cell }: { cell: Cell }) {
  return (
    <>
      <div className={`text-[14px] ${TONE[cell.tone]}`}>{cell.main}</div>
      {cell.detail && <div className="mt-0.5 font-mono text-[11px] text-ink3">{cell.detail}</div>}
    </>
  );
}

export function StretchTable({ data }: { data: Stretches }) {
  const [unit, setUnit] = useState<Unit>("gold");
  const opponent = new Map(data.vs_opponent.map((row) => [row.stretch, row]));
  // The opponent first, then peers before a target.
  const cohorts = Object.values(data.benchmarks).sort((a, b) => (a.audience === "peers" ? -1 : 1) - (b.audience === "peers" ? -1 : 1));
  const columns = [
    { key: "opponent", name: data.role === "JUNGLE" ? "Against the enemy jungler" : "Against the lane opponent" },
    ...cohorts.map((c) => ({ key: c.cohort, name: `Against ${rank(c.tier)}` })),
  ];
  const cell = (column: string, stretch: string): Cell => {
    if (column === "opponent") return opponentCell(opponent.get(stretch), unit);
    const cohort = data.benchmarks[column];
    return cohortCell(cohort, stretch, unit, rank(cohort.tier));
  };

  return (
    <div>
      <div role="radiogroup" aria-label="Show" className="flex gap-1.5">
        {(["gold", "cs"] as const).map((u) => (
          <button
            key={u}
            role="radio"
            aria-checked={unit === u}
            onClick={() => setUnit(u)}
            className={`rounded-[3px] border px-3 py-1 text-[13px] ${
              unit === u ? "border-ink3 bg-panel text-ink" : "border-rule text-ink2 hover:border-ink3/60"
            }`}
          >
            {u === "gold" ? "Gold" : "CS"}
          </button>
        ))}
      </div>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse">
          <thead>
            <tr>
              <th scope="col" className="smallcaps border-b border-rule pb-2 text-left font-normal text-ink3">
                Stretch
              </th>
              {columns.map(({ key, name }) => (
                <th key={key} scope="col" className="smallcaps border-b border-rule pb-2 text-left font-normal text-ink3">
                  {name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {STRETCHES.map(({ id, label }) => (
              <tr key={id} className="border-b border-rule/60 align-top">
                <th scope="row" className="py-3 pr-6 text-left text-[14px] font-normal text-ink">
                  {label}
                </th>
                {columns.map(({ key }) => (
                  <td key={key} className="py-3 pr-6">
                    <CellView cell={cell(key, id)} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
