import { describe, expect, it } from "vitest";

import type { CoachModel } from "./api";
import { costWords, pickModel } from "./models";

const model = (id: string, available: boolean, usd: number, isDefault = false): CoachModel => ({
  id,
  label: id,
  estimated_cost_usd: usd,
  available,
  reason: available ? null : "Not ready.",
  default: isDefault,
});

const MODELS = [
  model("claude-opus-5-5", true, 0.1048, true),
  model("claude-sonnet-5-5", true, 0.0529),
  model("claude-haiku-5-5", true, 0.0026),
  model("local", false, 0),
];

describe("picking a model", () => {
  it("keeps the remembered choice while it can answer", () => {
    expect(pickModel(MODELS, "claude-haiku-5-5")).toBe("claude-haiku-5-5");
  });

  it("falls back to the default when the remembered one can't answer", () => {
    expect(pickModel(MODELS, "local")).toBe("claude-opus-5-5");
    expect(pickModel(MODELS, null)).toBe("claude-opus-5-5");
  });

  it("uses whatever can answer when the default can't, such as with no Anthropic key", () => {
    const noKey = MODELS.map((m) => ({ ...m, available: m.id === "local" }));
    expect(pickModel(noKey, null)).toBe("local");
  });
});

describe("cost words", () => {
  it("rounds to cents, and says what the local model costs instead", () => {
    expect(costWords({ estimated_cost_usd: 0.1048 })).toBe("about $0.10 a question");
    expect(costWords({ estimated_cost_usd: 0.0026 })).toBe("under $0.01 a question");
    expect(costWords({ estimated_cost_usd: 0 })).toBe("Free, but several minutes per answer and less reliable");
  });
});
