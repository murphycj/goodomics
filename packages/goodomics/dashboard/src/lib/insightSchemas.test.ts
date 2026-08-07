import { describe, expect, it } from "vitest";
import { zSavedInsightRead } from "../api/generated/zod.gen";
import {
  insightDraftToCreate,
  reportDraftToCreate,
  savedInsightToDraft,
  savedReportToDraft,
} from "./insightSchemas";

const dates = {
  created_at: "2026-08-07T12:00:00Z",
  updated_at: "2026-08-07T12:00:00Z",
};

describe("generated response validation", () => {
  it("accepts meaningful nullable optionals at the wire boundary", () => {
    expect(() => zSavedInsightRead.parse({
      ...dates,
      insight_id: "insight-1",
      url_slug: "insight-1",
      project_id: "project-1",
      name: "Subject table",
      description: null,
      version: 1,
      analysis: {
        grain: "subject",
        values: [
          { field: "metadata/sample/sample_name", as: null, label: null, scope: null },
          { field: "metadata/sample/subject_id" },
          { field: "metadata/sample/sample_id" },
        ],
      },
      view: { kind: "table", hidden_values: [] },
    })).not.toThrow();
  });
});

describe("builder adapters", () => {
  it("normalizes nullable insight values and excludes read metadata on create", () => {
    const saved = zSavedInsightRead.parse({
      ...dates,
      insight_id: "insight-1",
      url_slug: "insight-1",
      project_id: "project-1",
      name: "Subject table",
      description: null,
      version: 1,
      analysis: {
        grain: "subject",
        values: [{ field: "metadata/sample/sample_name", as: null, label: null, scope: null }],
      },
      view: { kind: "table", hidden_values: [] },
    });
    const draft = savedInsightToDraft(saved);
    expect(draft.analysis.values[0]).toMatchObject({ aggregation: "raw", filters: [] });
    expect(draft.analysis.values[0]).not.toHaveProperty("as");
    const create = insightDraftToCreate(draft, {
      name: saved.name,
      project_id: saved.project_id,
    });
    expect(create).not.toHaveProperty("created_at");
    expect(create).not.toHaveProperty("url_slug");
  });

  it("materializes report defaults and produces a generated create contract", () => {
    const draft = savedReportToDraft({
      ...dates,
      report_id: "report-1",
      url_slug: "report-1",
      project_id: "project-1",
      name: "QC report",
      version: 1,
      insights: [{ id: "insight-1", layout: { x: 0, y: 0, width: 12, height: 4 } }],
    });
    expect(draft.layout).toEqual({ columns: 12, row_height: 64 });
    expect(reportDraftToCreate(draft, "project-1").project_id).toBe("project-1");
  });
});
