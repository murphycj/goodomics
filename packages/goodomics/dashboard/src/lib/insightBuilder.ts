/** Family-specific v2 insight-builder helpers. */

import type {
  FieldSelection,
  InsightDraft,
  InsightView,
  QueryKind,
  QueryNode,
  ViewKind,
} from "./insightSchemas";

export const QUERY_KINDS: QueryKind[] = [
  "rows",
  "summary",
  "relationship",
  "distribution",
  "series",
  "matrix",
  "alteration_matrix",
  "variant_position",
  "genome_profile",
  "survival",
  "timeline",
  "association",
];

const VIEWS_BY_QUERY: Record<QueryKind, ViewKind[]> = {
  rows: ["table", "bar", "stacked_bar"],
  summary: ["table", "bar", "stacked_bar", "line", "area", "pie", "donut", "metric"],
  relationship: ["scatter", "table"],
  distribution: ["histogram", "boxplot", "violin", "table"],
  series: ["line", "area", "table"],
  matrix: ["heatmap", "table"],
  alteration_matrix: ["oncoprint", "table"],
  variant_position: ["lollipop", "table"],
  genome_profile: ["genome_profile", "table"],
  survival: ["survival", "table"],
  timeline: ["timeline", "table"],
  association: ["association_matrix", "heatmap", "table"],
};

export function titleCase(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

/** Return views compatible with one typed query result. */
export function compatibleViews(kind: QueryKind): ViewKind[] {
  return VIEWS_BY_QUERY[kind];
}

/** Create a canonical field selection while preserving its public string. */
export function fieldSelection(field = ""): FieldSelection {
  return { field };
}

/** Create a complete query draft for one family. */
export function createQuery(kind: QueryKind): QueryNode {
  const field = fieldSelection();
  const common = { filters: [], order_by: [], limit: 1_000 };
  switch (kind) {
    case "rows": return { ...common, kind, grain: "sample", columns: [] };
    case "summary": return {
      ...common, kind, grain: "sample", group_by: [], calculations: [],
      aggregations: [{ ...field, aggregation: "count_distinct", as: "count" }],
    };
    case "relationship": return { ...common, kind, x: field, y: fieldSelection(), match_by: "sample" };
    case "distribution": return { ...common, kind, value: field, split_by: [], summaries: [] };
    case "series": return { ...common, kind, position: field, series_by: [], measurements: [fieldSelection()] };
    case "matrix": return { ...common, kind, rows: field, columns: fieldSelection(), value: fieldSelection(), cell_limit: 250_000 };
    case "alteration_matrix": return { ...common, kind, features: [], entities: [], alterations: [field], feature_set_ids: [], cell_limit: 250_000 };
    case "variant_position": return { ...common, kind, position: field, frequency: fieldSelection(), annotation_contract_ids: [] };
    case "genome_profile": return { ...common, kind, coordinate: field, value: fieldSelection(), group_by: [] };
    case "survival": return { ...common, kind, duration: field, event: fieldSelection(), group_by: [], provider: { method: "kaplan_meier", parameters: {} } };
    case "timeline": return { ...common, kind, subject: field, start: fieldSelection() };
    case "association": return { ...common, kind, features: [], state: [field], entities: [], feature_set_ids: [] };
  }
}

/** Create the default compatible view for a query family. */
export function createView(kind: QueryKind, requested?: ViewKind): InsightView {
  const viewKind = requested && compatibleViews(kind).includes(requested)
    ? requested
    : compatibleViews(kind)[0];
  if (viewKind === "table") return { kind: "table", hidden_values: [], sorting: [], numeric_format: {}, null_format: "—" };
  if (viewKind === "scatter") return { kind: "scatter", hidden_values: [] };
  if (viewKind === "metric") return { kind: "metric", hidden_values: [], thresholds: [] };
  if (viewKind === "histogram") return { kind: "histogram", hidden_values: [], bins: 20 };
  if (viewKind === "boxplot" || viewKind === "violin") return { kind: viewKind, hidden_values: [], colors: {} };
  if (viewKind === "heatmap") return { kind: "heatmap", hidden_values: [], colors: [], tooltips: [] };
  if (["bar", "stacked_bar", "line", "area", "pie", "donut"].includes(viewKind)) {
    return { kind: viewKind as "bar", hidden_values: [], colors: {}, tooltips: [] };
  }
  return { kind: viewKind as "oncoprint", hidden_values: [], options: {} };
}

/** Create an empty complete v2 definition. */
export function emptyInsightDraft(kind: QueryKind = "rows"): InsightDraft {
  return { version: 2, name: "New insight", query: createQuery(kind), view: createView(kind) };
}

/** Switch family without retaining incompatible family-specific properties. */
export function switchQueryFamily(draft: InsightDraft, kind: QueryKind): InsightDraft {
  return { ...draft, query: createQuery(kind), view: createView(kind) };
}
