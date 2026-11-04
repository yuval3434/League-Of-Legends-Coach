import { describe, expect, it } from "vitest";

import { keyStatus } from "./keys";

const NOW = new Date("2026-11-03T12:00:00Z");

describe("key status", () => {
  it("shows only the last 4 characters and the time left", () => {
    const info = { set: true, last4: "abcd", set_at: "2026-11-03T09:00:00Z", expires_at: "2026-11-04T09:00:00Z" };
    expect(keyStatus(info, NOW)).toEqual({ tone: "ok", words: "ending …abcd · expires in 21 h" });
  });

  it("warns in the last 2 hours and once expired", () => {
    const soon = { set: true, last4: "abcd", set_at: "x", expires_at: "2026-11-03T12:40:00Z" };
    const gone = { set: true, last4: "abcd", set_at: "x", expires_at: "2026-11-03T10:00:00Z" };
    expect(keyStatus(soon, NOW)).toEqual({ tone: "warn", words: "ending …abcd · expires in under 1 h" });
    expect(keyStatus(gone, NOW)).toEqual({ tone: "warn", words: "ending …abcd · expired 2 h ago" });
  });

  it("says when a key's age isn't known", () => {
    const old = { set: true, last4: "abcd", set_at: null, expires_at: null };
    expect(keyStatus(old, NOW).words).toBe("ending …abcd · set before this page, so its expiry isn't known");
  });

  it("has no expiry for the Anthropic key, and nothing for an unset key", () => {
    expect(keyStatus({ set: true, last4: "wxyz", set_at: "2026-11-03T09:00:00Z" }, NOW).words).toBe("ending …wxyz");
    expect(keyStatus({ set: false, last4: null, set_at: null }, NOW)).toEqual({ tone: "off", words: "Not set" });
  });
});
