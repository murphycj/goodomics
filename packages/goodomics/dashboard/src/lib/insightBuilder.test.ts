import { describe, expect, it } from "vitest";
import { compatibleViews, createQuery, emptyInsightDraft, switchQueryFamily } from "./insightBuilder";

describe("version 2 insight builder", () => {
  it("switches query families without retaining incompatible properties", () => {
    const draft = switchQueryFamily(emptyInsightDraft(), "relationship");
    expect(draft.version).toBe(2);
    expect(draft.query.kind).toBe("relationship");
    expect(draft.view.kind).toBe("scatter");
    expect("columns" in draft.query).toBe(false);
  });

  it("only returns compatible typed-result views", () => {
    expect(compatibleViews("survival")).toEqual(["survival", "table"]);
    expect(compatibleViews("matrix")).toEqual(["heatmap", "table"]);
  });

  it("starts common table and summary analyses at the sample grain", () => {
    expect(createQuery("rows")).toMatchObject({ grain: "sample", columns: [] });
    expect(createQuery("summary")).toMatchObject({ grain: "sample" });
  });

  it("starts a new draft with the selected analysis family and its default view", () => {
    const draft = emptyInsightDraft("relationship");
    expect(draft.query.kind).toBe("relationship");
    expect(draft.view.kind).toBe("scatter");
  });
});
