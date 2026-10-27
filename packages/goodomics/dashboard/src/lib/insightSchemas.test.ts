import { describe, expect, it } from "vitest";
import { insightDefinitionSchema, savedInsightReadSchema } from "./insightSchemas";

describe("version 2 insight schema", () => {
  it("preserves canonical field strings in a discriminated query", () => {
    const definition = insightDefinitionSchema.parse({
      version: 2,
      name: "Cancer types",
      query: {
        kind: "summary",
        grain: "subject",
        group_by: [{ field: "cbioportal:clinical:subjects/cancer_type" }],
        aggregations: [{ field: "metadata/subject/subject_id", aggregation: "count_distinct", as: "subjects" }],
      },
      view: { kind: "table" },
    });
    expect(definition.query.kind).toBe("summary");
    if (definition.query.kind === "summary") {
      expect(definition.query.group_by?.[0]?.field).toBe("cbioportal:clinical:subjects/cancer_type");
    }
  });

  it("parses saved responses with defaulted query and view discriminators", () => {
    const saved = savedInsightReadSchema.parse({
      created_at: "2026-08-12T12:00:00Z",
      description: null,
      insight_id: "insight-1",
      name: "Sample table",
      project_id: "project-1",
      query: {
        kind: "rows",
        grain: "sample",
        columns: [{ field: "metadata/sample/sample_id" }],
      },
      updated_at: "2026-08-12T12:00:00Z",
      url_slug: "ins_sample-table",
      version: 2,
      view: { kind: "table" },
    });

    expect(saved.query.kind).toBe("rows");
    expect(saved.view.kind).toBe("table");
  });
});
