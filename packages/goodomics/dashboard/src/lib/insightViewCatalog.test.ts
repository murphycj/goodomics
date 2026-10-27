import { describe, expect, it } from "vitest";
import { insightViewIconPath } from "./insightViewCatalog";

describe("insight view icon catalog", () => {
  it("maps saved view kinds to stable reusable PNG paths", () => {
    expect(insightViewIconPath("stacked_bar")).toBe("/plot-icons/stacked-bar.png");
    expect(insightViewIconPath("association_matrix")).toBe("/plot-icons/association-matrix.png");
  });

  it("uses a PNG fallback for an unknown view kind", () => {
    expect(insightViewIconPath("future_view")).toBe("/plot-icons/fallback.png");
  });
});
