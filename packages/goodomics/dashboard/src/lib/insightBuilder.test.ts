import { describe, expect, it } from "vitest";
import { zSavedInsightCreate } from "../api/generated/zod.gen";
import { reconcileView } from "./insightBuilder";
import type { AnalysisValue, InsightView } from "./insightSchemas";

const values: AnalysisValue[] = [
  { field: "metadata/subject/subject_id", aggregation: "raw", filters: [] },
  { field: "metadata/subject/cohort", aggregation: "raw", filters: [] },
  { field: "metadata/subject/status", aggregation: "raw", filters: [] },
];

const tableView: InsightView = {
  kind: "table",
  hidden_values: ["metadata/subject/cohort"],
  sorting: [],
  null_format: "—",
  numeric_format: {},
};

describe("table builder regressions", () => {
  it("validates a saved three-value subject-grain table", () => {
    expect(() => zSavedInsightCreate.parse({
      project_id: "project-1",
      name: "Subjects",
      version: 1,
      analysis: { grain: "subject", values },
      view: tableView,
    })).not.toThrow();
  });

  it("can hide and re-enable a table field without invalidating the draft", () => {
    const hidden = reconcileView(tableView, values, "subject");
    expect(hidden.hidden_values).toEqual(["metadata/subject/cohort"]);

    const visible = reconcileView(
      { ...hidden, hidden_values: [] },
      values,
      "subject",
    );
    expect(visible.hidden_values).toEqual([]);
    expect(() => zSavedInsightCreate.parse({
      name: "Subjects",
      version: 1,
      analysis: { grain: "subject", values },
      view: visible,
    })).not.toThrow();
  });

  it("drops removed hidden references and keeps restored fields visible", () => {
    const withoutCohort = reconcileView(
      tableView,
      [values[0], values[2]],
      "subject",
    );
    expect(withoutCohort.hidden_values).toEqual([]);

    const restored = reconcileView(withoutCohort, values, "subject");
    expect(restored.hidden_values).toEqual([]);
  });
});
