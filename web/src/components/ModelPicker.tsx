// Which model answers, under the chat box, with each one's estimated cost per
// question. A model that can't answer right now says why and can't be picked.

import type { CoachModel } from "../api";
import { costWords } from "../models";

export function ModelPicker({
  models,
  value,
  onChange,
  disabled,
  costs = true,
}: {
  models: CoachModel[];
  value: string | null;
  onChange: (id: string) => void;
  disabled?: boolean;
  // Off where the per-question estimate doesn't fit, such as Draft's options,
  // which shows its own ceiling for the board instead.
  costs?: boolean;
}) {
  return (
    <fieldset className="mt-5" disabled={disabled}>
      <legend className="smallcaps text-ink3">Model</legend>
      <div role="radiogroup" aria-label="Model" className="mt-2 grid gap-2 sm:grid-cols-2">
        {models.map((m) => {
          const on = m.id === value;
          return (
            <label
              key={m.id}
              className={`flex cursor-pointer items-baseline justify-between gap-3 rounded-[3px] border px-3.5 py-2.5 ${
                on ? "border-ink3 bg-panel" : "border-rule hover:border-ink3/60"
              } ${m.available ? "" : "cursor-not-allowed opacity-55"}`}
            >
              <span className="flex items-baseline gap-2.5">
                <input
                  type="radio"
                  name="model"
                  value={m.id}
                  checked={on}
                  disabled={!m.available}
                  onChange={() => onChange(m.id)}
                  className="translate-y-[1px] accent-[var(--color-ink)]"
                />
                <span className={`text-[14px] ${on ? "text-ink" : "text-ink2"}`}>{m.label}</span>
              </span>
              <span className="text-right font-mono text-[11px] text-ink3">
                {m.available ? (costs ? costWords(m) : "") : m.reason}
              </span>
            </label>
          );
        })}
      </div>
      {costs && (
      <p className="mt-2 text-[12px] text-ink3">
        Costs are estimates from the average question in the last eval; a model that writes more costs more. Every model
        gets the same tools, rules and number check.
      </p>
      )}
    </fieldset>
  );
}
