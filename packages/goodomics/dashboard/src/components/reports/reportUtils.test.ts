import { describe, expect, it } from "vitest";
import {
  applyReportGridLayout,
  reportGridLayoutsEqual,
  snapshotReportInsights,
  type ReportInsight,
} from "./reportUtils";

const insights: ReportInsight[] = [
  {
    id: "table-1",
    layout: { x: 0, y: 0, width: 6, height: 5 },
  },
  {
    id: "chart-1",
    layout: { x: 6, y: 0, width: 6, height: 5 },
  },
];

describe("report grid layout adapters", () => {
  it("updates portable width and height fields from grid geometry", () => {
    const next = applyReportGridLayout(insights, [
      { i: "table-1", x: 0, y: 0, w: 9, h: 7 },
      { i: "chart-1", x: 9, y: 0, w: 3, h: 7 },
    ]);

    expect(next).toEqual([
      {
        id: "table-1",
        layout: { x: 0, y: 0, width: 9, height: 7 },
      },
      {
        id: "chart-1",
        layout: { x: 9, y: 0, width: 3, height: 7 },
      },
    ]);
    expect(reportGridLayoutsEqual(insights, next)).toBe(false);
  });

  it("preserves insight objects when grid geometry has not changed", () => {
    const next = applyReportGridLayout(insights, [
      { i: "table-1", x: 0, y: 0, w: 6, h: 5 },
      { i: "chart-1", x: 6, y: 0, w: 6, h: 5 },
    ]);

    expect(next[0]).toBe(insights[0]);
    expect(next[1]).toBe(insights[1]);
    expect(reportGridLayoutsEqual(insights, next)).toBe(true);
  });

  it("copies nested layout values for a cancelable edit baseline", () => {
    const snapshot = snapshotReportInsights(insights);

    snapshot[0]!.layout.width = 12;

    expect(insights[0]!.layout.width).toBe(6);
    expect(snapshot[0]).not.toBe(insights[0]);
    expect(snapshot[0]!.layout).not.toBe(insights[0]!.layout);
  });
});
