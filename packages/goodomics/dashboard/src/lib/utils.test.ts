import { describe, expect, it } from "vitest";
import { formatRelativeTime } from "./utils";

describe("formatRelativeTime", () => {
  const now = new Date("2026-08-07T18:00:00Z");

  it.each([
    ["2026-08-07T17:15:00Z", "less than an hour ago"],
    ["2026-08-07T13:00:00Z", "5 hours ago"],
    ["2026-08-05T18:00:00Z", "2 days ago"],
    ["2026-05-07T18:00:00Z", "3 months ago"],
    ["2024-08-07T18:00:00Z", "2 years ago"],
  ])("formats %s as %s", (value, expected) => {
    expect(formatRelativeTime(value, now)).toBe(expected);
  });

  it("handles future timestamps", () => {
    expect(formatRelativeTime("2026-08-07T20:00:00Z", now)).toBe("in 2 hours");
  });
});
