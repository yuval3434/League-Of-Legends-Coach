// The evidence states, drawn the same way on every page.

export type State = "behind" | "ahead" | "watching" | "unclear" | "low";

const LABELS: Record<State, string> = {
  behind: "Finding",
  ahead: "Finding",
  watching: "Worth watching",
  unclear: "No clear gap",
  low: "Not enough data",
};

export function Marker({ state, size = 9 }: { state: State; size?: number }) {
  const s = size;
  return (
    <svg width={s} height={s} viewBox={`0 0 ${s} ${s}`} aria-hidden className="shrink-0">
      {state === "behind" && <rect width={s} height={s} className="fill-accent" />}
      {state === "ahead" && <rect width={s} height={s} className="fill-ink" />}
      {state === "watching" && (
        <rect x={0.5} y={0.5} width={s - 1} height={s - 1} className="fill-none stroke-ink2" />
      )}
      {state === "unclear" && <rect y={s / 2 - 0.5} width={s} height={1} className="fill-ink3" />}
      {state === "low" && (
        <>
          <rect width={s} height={s} fill="url(#hatch)" />
          <rect x={0.5} y={0.5} width={s - 1} height={s - 1} className="fill-none stroke-faint" />
        </>
      )}
    </svg>
  );
}

export function Verdict({ state, detail, label }: { state: State; detail?: string; label?: string }) {
  const tone =
    state === "behind" ? "text-accent" : state === "ahead" ? "text-ink" : state === "low" ? "text-ink3" : "text-ink2";
  return (
    <span className={`inline-flex items-center gap-2 smallcaps ${tone}`}>
      <Marker state={state} />
      <span>{label ?? LABELS[state]}</span>
      {detail && <span className="text-ink3 normal-case tracking-normal">· {detail}</span>}
    </span>
  );
}

/** Shared SVG defs: the hatch that marks data too thin to trust. */
export function HatchDefs() {
  return (
    <svg width={0} height={0} className="absolute" aria-hidden>
      <defs>
        <pattern id="hatch" width={4} height={4} patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width={4} height={4} fill="transparent" />
          <line x1={0} y1={0} x2={0} y2={4} stroke="#6f6c66" strokeWidth={1.5} />
        </pattern>
      </defs>
    </svg>
  );
}
