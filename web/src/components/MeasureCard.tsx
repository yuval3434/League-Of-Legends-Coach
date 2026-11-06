// One measure: your bar and the benchmark's, both from zero, with a plain
// verdict and the gap in words. Each bar ends exactly at its value. The margin
// decides the verdict but never touches the bars; its exact value waits
// behind a hover.

import { useEffect, useRef, useState } from "react";

import type { CompareRow, Role } from "../api";
import { barLengths } from "../bars";
import { fmt, gapWords, metricLabel, rowDecimals, signed, unit } from "../metrics";
import { type Subject, YOU, who, whoLower } from "../subject";
import { PLAIN, PLAIN_TONE } from "../verdict";
import { Marker, type State } from "./Verdict";

const BAR_COLOR: Record<State, string> = {
  behind: "var(--color-accent)",
  ahead: "var(--color-ink)",
  watching: "var(--color-ink2)",
  unclear: "var(--color-ink2)",
  low: "var(--color-faint)",
};

function useWidth<T extends HTMLElement>(): [React.RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    if (!ref.current) return;
    const observer = new ResizeObserver(([e]) => setWidth(e.contentRect.width));
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

/** A bar from zero that ends exactly at its value. */
function Bar({ length, color, label, hatched }: { length: number; color: string; label: string; hatched?: boolean }) {
  return (
    <svg width="100%" height={20} aria-hidden className="block overflow-visible">
      <rect
        className="bar-grow"
        x={0}
        y={4}
        width={length}
        height={12}
        rx={2}
        fill={hatched ? "url(#hatch)" : color}
        stroke={hatched ? "var(--color-faint)" : "none"}
      />
      <text x={length + 6} y={14.5} className="fill-ink2 text-[12px]">
        {label}
      </text>
    </svg>
  );
}

export function VerdictLine({ state, words }: { state: State; words: string }) {
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[14px]">
      <Marker state={state} size={8} />
      <span className={`font-medium ${PLAIN_TONE[state]}`}>{PLAIN[state]}</span>
      {words && <span className="text-ink3">· {words}</span>}
    </div>
  );
}

/** The exact numbers, for anyone who wants them: shown on hover only. */
function Margins({ row, cohort, subject }: { row: CompareRow; cohort: string; subject: Subject }) {
  const d = rowDecimals(row);
  const mine = row.my_margin !== null ? `±${fmt(row.my_margin, d)}` : "no margin";
  const theirs = row.benchmark_margin !== null ? `±${fmt(row.benchmark_margin, d)}` : "no margin";
  return (
    <div className="pointer-events-none absolute left-0 top-full z-10 mt-1 rounded-[3px] border border-rule bg-panel px-3 py-2 font-mono text-[11px] leading-relaxed text-ink2 opacity-0 shadow-lg shadow-black/40 transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100">
      {whoLower(subject)} {fmt(row.my_value, d)} {mine} · {row.my_sample} games
      <br />
      {cohort} {fmt(row.benchmark_value, d)} {theirs} · {row.benchmark_sample} games
      <br />
      gap {signed(row.difference, d)}
      {row.difference_margin !== null ? ` ±${fmt(row.difference_margin, d)}` : ""}
    </div>
  );
}

export function MeasureCard({
  row,
  state,
  cohort,
  subject = YOU,
  role = "JUNGLE",
}: {
  row: CompareRow;
  state: State;
  cohort: string;
  subject?: Subject;
  role?: Role;
}) {
  const d = rowDecimals(row);
  const suffix = unit(row.value);
  const mine = row.my_value;
  const theirs = row.benchmark_value;
  const [ref, width] = useWidth<HTMLDivElement>();
  const labelRoom = 64;
  const bars = barLengths(row, Math.max(width - 52 - labelRoom, 0));
  return (
    <div tabIndex={0} className="group relative border-t border-rule pt-4 pb-3 outline-none">
      <div className="text-[15px] text-ink">{metricLabel(row, role)}</div>
      {bars ? (
        <div ref={ref} className="mt-3 grid grid-cols-[52px_1fr] items-center gap-y-1.5 text-[12px]">
          <span className="truncate text-ink" title={who(subject)}>
            {who(subject)}
          </span>
          <Bar length={bars.mine} color={BAR_COLOR[state]} label={`${fmt(mine, d)}${suffix}`} hatched={state === "low"} />
          <span className="text-ink3">{cohort}</span>
          <Bar length={bars.theirs} color="var(--color-ink3)" label={`${fmt(theirs, d)}${suffix}`} />
        </div>
      ) : (
        <div className="mt-3 text-[14px] text-ink2">
          {who(subject)} <span className="text-ink">{signed(mine, d)}</span> · {cohort} {signed(theirs, d)}
        </div>
      )}
      <div className="mt-3">
        {row.context_only ? (
          <div className="text-[14px] text-ink3">Context, not judged{state === "low" ? "" : ` · ${gapWords(row, cohort)}`}</div>
        ) : (
          <VerdictLine state={state} words={state === "low" ? "" : gapWords(row, cohort)} />
        )}
      </div>
      <Margins row={row} cohort={cohort} subject={subject} />
    </div>
  );
}
