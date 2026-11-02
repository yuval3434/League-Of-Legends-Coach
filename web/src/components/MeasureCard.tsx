// One measure: your bar and the benchmark's, both from zero, with a plain
// verdict and the gap in words. The margin decides the verdict and shows as a
// fade at each bar's end; its exact value waits behind a hover.

import { useEffect, useId, useRef, useState } from "react";

import type { CompareRow } from "../api";
import { fmt, gapWords, metricLabel, rowDecimals, signed, unit } from "../metrics";
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

/** A bar from zero. Solid as far as the value is certain, then it fades out. */
function Bar({
  value,
  margin,
  max,
  color,
  label,
  hatched,
}: {
  value: number;
  margin: number;
  max: number;
  color: string;
  label: string;
  hatched?: boolean;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const id = useId().replace(/:/g, "");
  const labelRoom = 64;
  const plot = Math.max(width - labelRoom, 0);
  const far = value + margin;
  const sure = Math.max(value - margin, 0);
  return (
    <div ref={ref} className="h-5 w-full">
      {width > 0 && (
        <svg width={width} height={20} aria-hidden>
          <defs>
            <linearGradient id={id} x1="0" x2="1" y1="0" y2="0">
              <stop offset={far ? sure / far : 1} stopColor={color} stopOpacity={1} />
              <stop offset={1} stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <rect
            className="bar-grow"
            x={0}
            y={4}
            width={(far / max) * plot}
            height={12}
            rx={2}
            fill={hatched ? "url(#hatch)" : `url(#${id})`}
            stroke={hatched ? "var(--color-faint)" : "none"}
          />
          <text x={(far / max) * plot + 6} y={14.5} className="fill-ink2 text-[12px]">
            {label}
          </text>
        </svg>
      )}
    </div>
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
function Margins({ row, cohort }: { row: CompareRow; cohort: string }) {
  const d = rowDecimals(row);
  const mine = row.my_margin !== null ? `±${fmt(row.my_margin, d)}` : "no margin";
  const theirs = row.benchmark_margin !== null ? `±${fmt(row.benchmark_margin, d)}` : "no margin";
  return (
    <div className="pointer-events-none absolute left-0 top-full z-10 mt-1 rounded-[3px] border border-rule bg-panel px-3 py-2 font-mono text-[11px] leading-relaxed text-ink2 opacity-0 shadow-lg shadow-black/40 transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100">
      you {fmt(row.my_value, d)} {mine} · {row.my_sample} games
      <br />
      {cohort} {fmt(row.benchmark_value, d)} {theirs} · {row.benchmark_sample} games
      <br />
      gap {signed(row.difference, d)}
      {row.difference_margin !== null ? ` ±${fmt(row.difference_margin, d)}` : ""}
    </div>
  );
}

export function MeasureCard({ row, state, cohort }: { row: CompareRow; state: State; cohort: string }) {
  const d = rowDecimals(row);
  const suffix = unit(row.value);
  const mine = row.my_value;
  const theirs = row.benchmark_value;
  // Gaps against an opponent can be negative: bars from zero can't show them.
  const asBars = mine !== null && theirs !== null && mine >= 0 && theirs >= 0;
  const max = asBars
    ? Math.max(mine + (row.my_margin ?? 0), theirs + (row.benchmark_margin ?? 0)) || 1
    : 1;
  return (
    <div tabIndex={0} className="group relative border-t border-rule pt-4 pb-3 outline-none">
      <div className="text-[15px] text-ink">{metricLabel(row)}</div>
      {asBars ? (
        <div className="mt-3 grid grid-cols-[52px_1fr] items-center gap-y-1.5 text-[12px]">
          <span className="text-ink">You</span>
          <Bar
            value={mine}
            margin={row.my_margin ?? 0}
            max={max}
            color={BAR_COLOR[state]}
            label={`${fmt(mine, d)}${suffix}`}
            hatched={state === "low"}
          />
          <span className="text-ink3">{cohort}</span>
          <Bar
            value={theirs}
            margin={row.benchmark_margin ?? 0}
            max={max}
            color="var(--color-ink3)"
            label={`${fmt(theirs, d)}${suffix}`}
          />
        </div>
      ) : (
        <div className="mt-3 text-[14px] text-ink2">
          You <span className="text-ink">{signed(mine, d)}</span> · {cohort} {signed(theirs, d)}
        </div>
      )}
      <div className="mt-3">
        <VerdictLine state={state} words={state === "low" ? "" : gapWords(row, cohort)} />
      </div>
      <Margins row={row} cohort={cohort} />
    </div>
  );
}
