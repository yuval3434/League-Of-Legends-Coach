import { describe, expect, it } from "vitest";

import { metricLabel } from "./metrics";

describe("metric labels", () => {
  it("names the opponent by role", () => {
    const row = { value: "avg_gold_diff", minute: 10 };
    expect(metricLabel(row)).toBe("Gold vs enemy jungler, 10 min");
    expect(metricLabel(row, "MIDDLE")).toBe("Gold vs lane opponent, 10 min");
  });

  it("names the new role measures", () => {
    expect(metricLabel({ value: "avg_lane_plates" })).toBe("Enemy plates in the lane, before 14 min");
    expect(metricLabel({ value: "avg_damage_share_pct" })).toBe("Share of the team's damage");
    expect(metricLabel({ value: "avg_roam_takedowns" })).toBe("Takedowns away from mid, before 14 min");
  });
});
