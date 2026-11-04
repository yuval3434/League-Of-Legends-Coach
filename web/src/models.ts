// The coach model picker: which model to start on, and each one's cost in words.
// The estimates come from the server; the page only words them.

import type { CoachModel } from "./api";

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
