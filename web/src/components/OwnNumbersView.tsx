// A player's own numbers in one role, for when no benchmark fits yet: each
// measure over all their games, and in their wins and losses apart. Nothing
// from anyone else's games, and nothing in place of a benchmark.

import type { OwnNumbers, OwnRow, OwnSide } from "../api";
import { fmt, metricLabel, unit } from "../metrics";
import { roleWord } from "../offers";
import { shownRows, winLossWords } from "../own";
import { type Subject, whose, Whose } from "../subject";

const THEMES: Record<string, string> = {
  economy: "Farm and gold",
  vision: "Vision",
  deaths: "Deaths",
  fights: "Fights",
  objectives: "Plates",
};

function Cell({ side, row }: { side: OwnSide; row: OwnRow }) {
  const suffix = unit(row.value);
  return (
    <td className="py-2 pr-5">
      <div className={`font-mono ${side.low_sample ? "text-ink3" : "text-ink"}`}>
        {side.value === null ? "—" : `${fmt(side.value)}${suffix}`}
        {side.margin !== null && side.value !== null && (
          <span className="text-ink3">
            {" "}
            ±{fmt(side.margin)}
            {suffix}
          </span>
        )}
      </div>
      <div className="font-mono text-[11px] text-ink3">
        {side.sample} {row.sample_unit}
        {side.low_sample ? " · too early to tell" : ""}
      </div>
    </td>
  );
}

export function OwnNumbersView({ data, s }: { data: OwnNumbers; s: Subject }) {
  const rows = shownRows(data.rows);
  if (!rows.length) return null;
  const themes = Object.keys(THEMES).filter((t) => rows.some((r) => r.theme === t));
  return (
    <section className="mt-14">
      <div className="smallcaps text-ink3">On {whose(s)} own</div>
      <h2 className="display mt-2 text-[28px] leading-tight">
        {Whose(s)} {data.games} {roleWord(data.role)} games, without a benchmark
      </h2>
      <p className="mt-3 max-w-[700px] text-[15px] text-ink2">
        Every number here is from {whose(s)} own games. Wins and losses are split to show which measures move with the
        result. {data.notes[0]}
      </p>
      <div className="relative mt-6 overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-[14px]">
          <thead>
            <tr>
              {["", "All games", "In wins", "In losses", "Wins against losses"].map((h) => (
                <th key={h || "measure"} scope="col" className="smallcaps border-b border-rule pb-2 pr-5 text-left font-normal text-ink3">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          {themes.map((theme) => (
            <tbody key={theme}>
              <tr>
                <th colSpan={5} scope="colgroup" className="pt-5 pb-1 text-left text-[13px] font-normal text-ink3">
                  {theme === "objectives" && data.role === "JUNGLE" ? "Objectives" : THEMES[theme]}
                </th>
              </tr>
              {rows
                .filter((r) => r.theme === theme)
                .map((row) => (
                  <tr key={`${row.metric}-${row.value}-${row.minute ?? ""}-${row.phase ?? ""}`} className="border-b border-rule/60 align-top">
                    <th scope="row" className="py-2 pr-5 text-left font-normal text-ink2">
                      {metricLabel(row, data.role)}
                    </th>
                    <Cell side={row.all} row={row} />
                    <Cell side={row.wins} row={row} />
                    <Cell side={row.losses} row={row} />
                    <td className={`py-2 pr-5 ${row.clear_gap ? "text-ink" : "text-ink3"}`}>{winLossWords(row)}</td>
                  </tr>
                ))}
            </tbody>
          ))}
        </table>
      </div>
    </section>
  );
}
