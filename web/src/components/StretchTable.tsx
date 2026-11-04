// Gold or CS by stretch of the game, against the enemy jungler and each cohort.
// A cell with too few games says so instead of giving an amount, and a cohort
// that doesn't fit the player says "No benchmark". Never part of a finding.

import { useState } from "react";

import type { Stretches } from "../api";
import { cohortCell, type Cell, junglerCell, STRETCHES, type Tone, type Unit } from "../stretches";

const TONE: Record<Tone, string> = { clear: "text-ink", unclear: "text-ink2", low: "text-ink3" };

const COLUMNS = [
  { key: "jungler", name: "Against the enemy jungler" },
  { key: "silver", name: "Against Silver" },
  { key: "emerald", name: "Against Emerald" },
] as const;

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
  const jungler = new Map(data.vs_enemy_jungler.map((row) => [row.stretch, row]));
  const cell = (column: (typeof COLUMNS)[number]["key"], stretch: string): Cell =>
    column === "jungler"
      ? junglerCell(jungler.get(stretch), unit)
      : cohortCell(data.benchmarks[column], stretch, unit, column === "silver" ? "Silver" : "Emerald");

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
              {COLUMNS.map(({ key, name }) => (
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
                {COLUMNS.map(({ key }) => (
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
