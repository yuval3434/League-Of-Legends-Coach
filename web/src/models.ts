// The coach model picker: which model to start on, and each one's cost in words.
// The estimates come from the server; the page only words them.

import type { CoachModel } from "./api";

/** The local model's last full eval run, which LOCAL_LIMITS sums up. */
export const LOCAL_EVAL_URL = "https://github.com/yuval3434/League-Of-Legends-Coach/blob/main/docs/EVAL.md#the-full-run-on-a-local-model";

/**
 * What the local model gets wrong, from its last full eval run (16 questions on
 * qwen3:4b, 2026-11-08). Shown next to the model picker when it's chosen.
 */
export const LOCAL_LIMITS = [
  "It's slow: about 13 minutes an answer, and 4 of the 16 questions timed out.",
  "It picked a champion for you in the draft, and claimed it counters the enemy, which no data shows.",
  "It compared with Emerald where the data says the two can't be compared.",
  "It listed a gap with no verdict as something to work on.",
  "Its numbers were all in the data, but one was put under the wrong stat.",
];

export const MODEL_STORE = "lolcoach.coach.model";

/** The remembered choice if it can answer, else the server's default, else any that can. */
export function pickModel(models: CoachModel[], remembered: string | null): string | null {
  const ready = (id: string | null | undefined) => models.find((m) => m.id === id && m.available)?.id;
  return (
    ready(remembered) ??
    ready(models.find((m) => m.default)?.id) ??
    models.find((m) => m.available)?.id ??
    remembered ??
    models[0]?.id ??
    null
  );
}

/** "about $0.10 a question", "under $0.01 a question", "Free, but several minutes per answer and less reliable". */
export function costWords(model: Pick<CoachModel, "estimated_cost_usd">): string {
  const usd = model.estimated_cost_usd;
  if (usd === 0) return "Free, but several minutes per answer and less reliable";
  if (usd < 0.01) return "under $0.01 a question";
  return `about $${usd.toFixed(2)} a question`;
}
