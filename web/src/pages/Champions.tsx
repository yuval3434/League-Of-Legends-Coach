// Every champion you've played: a role filter, a table sorted by any column in
// one click, and a hand-off to the coach. Champions on fewer than 10 games are
// drawn in the "too early to tell" style wherever the sort puts them.

import { useEffect, useState } from "react";

import { api, type ChampionRow, type Role } from "../api";
import { ChampionIcon } from "../components/ChampionIcon";
import { Layout } from "../components/Layout";
import { Marker } from "../components/Verdict";
import { nextSort, rangeWords, roleSplit, sortChampions, type Sort, type SortKey } from "../champions";
import { usePlayer } from "../player";
import { type Subject, subjectOf, YOU, Whose } from "../subject";
import { useChampionNames } from "../ddragon";
import { fmt } from "../metrics";
import { askCoach } from "../router";

const ROLES: { id: Role | null; label: string; where: string }[] = [
  { id: null, label: "All roles", where: "" },
  { id: "JUNGLE", label: "Jungle", where: " in the jungle" },
  { id: "TOP", label: "Top", where: " in top lane" },
  { id: "MIDDLE", label: "Mid", where: " in mid lane" },
  { id: "BOTTOM", label: "Bot", where: " in bot lane" },
  { id: "UTILITY", label: "Support", where: " as support" },
];

const COLUMNS: { key: SortKey; label: string; numeric: boolean }[] = [
  { key: "champion", label: "Champion", numeric: false },
  { key: "games", label: "Games", numeric: true },
  { key: "win_rate_pct", label: "Win rate", numeric: true },
  { key: "kda", label: "KDA", numeric: true },
  { key: "cs_per_min", label: "CS per min", numeric: true },
];

/** Win rate on a 0–100 scale with a tick at 50%. The bar ends at the value. */
function WinRateBar({ value, low }: { value: number; low: boolean }) {
  const width = 96;
  return (
    <svg width={width} height={12} aria-hidden className="shrink-0">
      <rect x={0} y={5} width={width} height={2} className="fill-rule" />
      <rect
        x={0}
        y={2}
        width={(value / 100) * width}
        height={8}
        rx={1.5}
        fill={low ? "url(#hatch)" : "var(--color-ink2)"}
        stroke={low ? "var(--color-faint)" : "none"}
      />
      <rect x={width / 2 - 0.5} y={0} width={1} height={12} className="fill-ink3" />
    </svg>
  );
}

function RoleFilter({ role, onChange }: { role: Role | null; onChange: (role: Role | null) => void }) {
  return (
    <div role="radiogroup" aria-label="Role" className="flex flex-wrap gap-x-1 gap-y-2">
      {ROLES.map((r) => {
        const on = r.id === role;
        return (
          <button
            key={r.label}
            role="radio"
            aria-checked={on}
            onClick={() => onChange(r.id)}
            className={`rounded-[3px] px-3 py-1.5 text-[14px] ${
              on ? "bg-ink text-page" : "text-ink2 hover:bg-panel hover:text-ink"
            }`}
          >
            {r.label}
          </button>
        );
      })}
    </div>
  );
}

function HeaderCell({ column, sort, onSort }: { column: (typeof COLUMNS)[number]; sort: Sort; onSort: (key: SortKey) => void }) {
  const active = sort.key === column.key;
  const arrow = active ? (sort.descending ? "↓" : "↑") : "";
  return (
    <th
      scope="col"
      aria-sort={active ? (sort.descending ? "descending" : "ascending") : "none"}
      className={`border-b border-rule pb-2 font-normal ${column.numeric ? "text-right" : "text-left"}`}
    >
      <button
        onClick={() => onSort(column.key)}
        className={`smallcaps relative hover:text-ink ${active ? "text-ink" : "text-ink3"}`}
      >
        {column.label}
        {/* The arrow hangs outside the label so headers line up with their numbers. */}
        <span className={`absolute top-0 ${column.numeric ? "right-full mr-1" : "left-full ml-1"}`}>{arrow}</span>
      </button>
    </th>
  );
}

function ChampionTableRow({
  row,
  name,
  subject,
  allRoles,
}: {
  row: ChampionRow;
  name: string;
  subject: Subject;
  allRoles: boolean;
}) {
  const low = row.low_sample ?? false;
  const tone = low ? "text-ink3" : "text-ink";
  return (
    <tr className="group border-b border-rule/60 hover:bg-panel">
      <td className="py-2.5 pr-4">
        <div className="flex items-center gap-3">
          <span className={low ? "opacity-60" : ""}>
            <ChampionIcon champion={row.champion} size={30} />
          </span>
          <span className={`text-[15px] ${tone}`}>{name}</span>
        </div>
      </td>
      <td className={`py-2.5 pl-4 text-right ${tone}`}>
        {/* Under "All roles", the split by role waits behind a hover or focus. */}
        <span
          tabIndex={allRoles ? 0 : undefined}
          className="group/games relative inline-flex items-center gap-2 outline-none"
        >
          {low && <Marker state="low" size={8} />}
          {row.games}
          {allRoles && (
            <span
              role="tooltip"
              className="pointer-events-none absolute bottom-full right-0 z-10 mb-1.5 w-max max-w-[300px] rounded-[3px] border border-rule bg-panel px-3 py-2 text-left text-[13px] leading-relaxed text-ink2 opacity-0 shadow-lg shadow-black/40 transition-opacity duration-150 group-hover/games:opacity-100 group-focus/games:opacity-100"
            >
              {roleSplit(row)}
            </span>
          )}
        </span>
      </td>
      <td className="py-2.5 pl-4">
        {/* The range waits behind a hover or focus, like the Overview's margins. */}
        <div tabIndex={0} className="group/rate relative flex items-center justify-end gap-3 outline-none">
          <span className={tone}>{fmt(row.win_rate_pct, 1)}%</span>
          <WinRateBar value={row.win_rate_pct} low={low} />
          <div
            role="tooltip"
            className="pointer-events-none absolute bottom-full right-0 z-10 mb-1.5 w-[340px] rounded-[3px] border border-rule bg-panel px-3 py-2 text-left text-[13px] leading-relaxed text-ink2 opacity-0 shadow-lg shadow-black/40 transition-opacity duration-150 group-hover/rate:opacity-100 group-focus/rate:opacity-100"
          >
            {rangeWords(row, subject)}
          </div>
        </div>
      </td>
      <td className={`py-2.5 pl-4 text-right ${tone}`}>{fmt(row.kda, 2)}</td>
      <td className={`py-2.5 pl-4 text-right ${tone}`}>{fmt(row.cs_per_min, 2)}</td>
      <td className="py-2.5 pl-6 text-right">
        {/* Under 10 games the coach could only say "not enough data", and asking costs money. */}
        {!low && (
          <a
            href={askCoach(
              subject.you
                ? `How am I doing on ${name}, and what should I work on?`
                : `How is ${subject.name} doing on ${name}, and what should they work on?`,
            )}
            className="whitespace-nowrap text-[13px] text-faint underline decoration-transparent underline-offset-4 group-hover:text-ink2 group-hover:decoration-ink3 hover:!text-ink focus-visible:text-ink focus-visible:decoration-ink3"
          >
            Ask the coach
          </a>
        )}
      </td>
    </tr>
  );
}

export function Champions() {
  const [role, setRole] = useState<Role | null>(null);
  const [rows, setRows] = useState<ChampionRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sort, setSort] = useState<Sort>({ key: "games", descending: true });
  const [hideLow, setHideLow] = useState(false);
  const name = useChampionNames();
  const { puuid, player } = usePlayer();
  const s = player ? subjectOf(player) : YOU;

  useEffect(() => {
    setRows(null);
    setError(null);
    api.champions(role, puuid).then(setRows).catch((e: Error) => setError(e.message));
  }, [role, puuid]);

  const sorted = rows ? sortChampions(rows, sort, name) : [];
  const shown = hideLow ? sorted.filter((r) => !r.low_sample) : sorted;
  const judged = rows?.filter((r) => !r.low_sample).length ?? 0;
  const where = ROLES.find((r) => r.id === role)!.where;

  return (
    <Layout active="champions">
      <div className="pt-12">
        <div className="smallcaps text-ink3">Champions</div>
        <h1 className="display mt-1.5 max-w-[920px] text-[50px] leading-[1.02]">
          {rows === null
            ? `${Whose(s)} champions`
            : `${rows.length} champions played, ${judged} with enough games to judge`}
        </h1>
        <p className="mt-5 max-w-[700px] text-[16px] text-ink2">
          Ranked games{where}, remakes left out. A
          champion on fewer than 10 games is hatched and greyed: its win rate could swing a long way on the next few
          games. Click any column to sort by it.
        </p>
      </div>

      <div className="mt-10 flex flex-wrap items-center justify-between gap-x-8 gap-y-4">
        <RoleFilter role={role} onChange={setRole} />
        <label className="inline-flex cursor-pointer items-center gap-2 text-[14px] text-ink2">
          <input
            type="checkbox"
            checked={hideLow}
            onChange={(e) => setHideLow(e.target.checked)}
            className="h-3.5 w-3.5 accent-[var(--color-ink)]"
          />
          Hide champions under 10 games
        </label>
      </div>

      {error && <p className="mt-10 text-ink2">{error}</p>}
      {!error && rows === null && <p className="mt-10 font-mono text-[12px] text-ink3">Loading champions…</p>}
      {rows !== null && rows.length === 0 && (
        <p className="mt-10 text-ink2">No ranked games{where} yet.</p>
      )}
      {rows !== null && rows.length > 0 && (
        <div className="relative mt-6 overflow-x-auto">
          <table className="w-full min-w-[760px] border-collapse text-[14px]">
            <colgroup>
              <col className="w-[30%]" />
              <col className="w-[10%]" />
              <col className="w-[22%]" />
              <col className="w-[10%]" />
              <col className="w-[12%]" />
              <col />
            </colgroup>
            <thead>
              <tr>
                {COLUMNS.map((c) => (
                  <HeaderCell key={c.key} column={c} sort={sort} onSort={(key) => setSort(nextSort(sort, key))} />
                ))}
                <th className="border-b border-rule pb-2">
                  <span className="sr-only">Ask the coach</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {shown.map((row) => (
                <ChampionTableRow
                  key={row.champion}
                  row={row}
                  name={name(row.champion)}
                  subject={s}
                  allRoles={role === null}
                />
              ))}
            </tbody>
          </table>
          {hideLow && shown.length === 0 && (
            <p className="mt-6 text-ink2">No champion has 10 games{where} yet.</p>
          )}
        </div>
      )}

      <div className="mt-6 flex items-center gap-2 text-[13px] text-ink3">
        <Marker state="low" size={8} /> Too early to tell: fewer than 10 games. The tick on each bar marks 50%; hover a win rate for its range.
      </div>
    </Layout>
  );
}
