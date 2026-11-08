// A value by minute for you and each cohort: a line for each average and a
// shaded band for your 95% margin. Hovering a minute gives the exact numbers
// and the gaps in words.

import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipProps,
} from "recharts";

import { type MinutePoint, type Series } from "../compare";
import { fmt, gapWords, rowDecimals } from "../metrics";
import { type Subject, who, whoIs, whose } from "../subject";

type ChartLine = { key: Series; label: string; color: string; dash?: string; width: number };

/**
 * The lines to draw: the player, then each cohort that has a benchmark for
 * them. A cohort that doesn't fit gets no line at all, never a stand-in.
 */
export function seriesFor(subject: Subject, names: { peers?: string; target?: string }): ChartLine[] {
  const lines: ChartLine[] = [{ key: "you", label: who(subject), color: "var(--color-ink)", width: 2.5 }];
  if (names.target) lines.push({ key: "target", label: names.target, color: "var(--color-ink2)", dash: "6 4", width: 2 });
  if (names.peers) lines.push({ key: "peers", label: names.peers, color: "var(--color-ink3)", width: 2 });
  return lines;
}

/** The key under the chart titles: each line's stroke beside its name. */
export function SeriesKey({ series, subject }: { series: ChartLine[]; subject: Subject }) {
  return (
    <div className="flex flex-wrap gap-x-6 gap-y-2 text-[13px] text-ink2">
      {series.map((s) => (
        <span key={s.key} className="inline-flex items-center gap-2">
          <svg width={26} height={8} aria-hidden>
            <line x1={0} x2={26} y1={4} y2={4} stroke={s.color} strokeWidth={s.width} strokeDasharray={s.dash} />
          </svg>
          {s.label}
        </span>
      ))}
      <span className="inline-flex items-center gap-2">
        <svg width={26} height={10} aria-hidden>
          <rect width={26} height={10} fill="var(--color-ink)" opacity={0.14} />
        </svg>
        Shading: {whose(subject)} likely range
      </span>
    </div>
  );
}

function MinuteTooltip({
  active,
  payload,
  subject,
  series,
}: TooltipProps<number, string> & { subject: Subject; series: ChartLine[] }) {
  const point = payload?.[0]?.payload as MinutePoint | undefined;
  if (!active || !point) return null;
  const label = (key: Series) => series.find((s) => s.key === key)?.label ?? key;
  const mine = point.peersRow ?? point.targetRow;
  // Keep each value's own precision: 106.0, not 106.
  const d = mine ? Math.max(rowDecimals(mine), point.targetRow ? rowDecimals(point.targetRow) : 0) : undefined;
  return (
    <div className="rounded-[3px] border border-rule bg-panel px-3 py-2 text-[13px] leading-relaxed text-ink2 shadow-lg shadow-black/40">
      <div className="smallcaps text-ink3">{point.minute} min</div>
      <div>
        <span className="text-ink">
          {who(subject)} {fmt(point.you, d)}
        </span>
        {mine && <span className="text-ink3"> · {mine.my_sample} games</span>}
      </div>
      {point.peersRow && (
        <div>
          {label("peers")} {fmt(point.peers, d)}{" "}
          <span className="text-ink3">
            · {subject.you ? "you're" : whoIs(subject)} {gapWords(point.peersRow, label("peers"))}
          </span>
        </div>
      )}
      {point.targetRow && (
        <div>
          {label("target")} {fmt(point.target, d)}{" "}
          <span className="text-ink3">
            · {subject.you ? "you're" : whoIs(subject)} {gapWords(point.targetRow, label("target"))}
          </span>
        </div>
      )}
    </div>
  );
}

/** The series' name at the end of its line, so the chart reads without the key. */
function endLabel(series: ChartLine, last: number) {
  return function Label(props: { x?: number; y?: number; index?: number }) {
    // Recharts wants an element for every point; the others get an empty group.
    if (props.index !== last || props.x === undefined || props.y === undefined) return <g />;
    return (
      <text x={props.x + 10} y={props.y + 4} className="text-[12px]" fill={series.color}>
        {series.label}
      </text>
    );
  };
}

export function MinuteChart({
  points,
  unitLabel,
  series,
  subject,
}: {
  points: MinutePoint[];
  unitLabel: string;
  series: ChartLine[];
  subject: Subject;
}) {
  const last = points.length - 1;
  const names = series.map((s) => s.label).join(", ");
  return (
    <div className="h-[300px] w-full" role="img" aria-label={`${unitLabel} at 10, 15 and 20 minutes for ${names}`}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={points} margin={{ top: 12, right: 72, bottom: 4, left: 4 }}>
          <CartesianGrid vertical={false} stroke="var(--color-rule)" />
          <XAxis
            dataKey="minute"
            type="number"
            domain={[10, 20]}
            ticks={[10, 15, 20]}
            tickFormatter={(m: number) => `${m} min`}
            stroke="var(--color-rule)"
            tick={{ fill: "var(--color-ink3)", fontSize: 12 }}
            tickLine={false}
          />
          <YAxis
            domain={["auto", "auto"]}
            tickFormatter={(v: number) => fmt(v, 0)}
            width={52}
            axisLine={false}
            tickLine={false}
            tick={{ fill: "var(--color-ink3)", fontSize: 12 }}
          />
          <Tooltip content={<MinuteTooltip subject={subject} series={series} />} cursor={{ stroke: "var(--color-ink3)", strokeDasharray: "2 3" }} />
          {/* Only your band: the benchmarks rest on ~500 games, so theirs are a hairline. */}
          <Area
            dataKey="youBand"
            stroke="none"
            fill="var(--color-ink)"
            fillOpacity={0.14}
            isAnimationActive={false}
            activeDot={false}
            connectNulls
          />
          {series.map((s) => (
            <Line
              key={s.key}
              dataKey={s.key}
              stroke={s.color}
              strokeWidth={s.width}
              strokeDasharray={s.dash}
              dot={{ r: 4, fill: "var(--color-page)", stroke: s.color, strokeWidth: 2, strokeDasharray: "0" }}
              activeDot={{ r: 5, fill: s.color, stroke: "var(--color-page)", strokeWidth: 2, strokeDasharray: "0" }}
              label={endLabel(s, last)}
              isAnimationActive={false}
              connectNulls
            />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
