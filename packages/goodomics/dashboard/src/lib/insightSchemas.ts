/** Frontend-only builder drafts and adapters around generated API contracts. */

import { z } from "zod";
import type {
  AnalysisValue as ApiAnalysisValue,
  BoxplotView,
  CategoryChartView,
  HeatmapView,
  HistogramView,
  InsightFilter,
  MetricView,
  ReportInsight,
  ResultScope as ApiResultScope,
  SavedInsightCreate,
  SavedInsightPatch,
  SavedInsightRead,
  SavedReportCreate,
  SavedReportPatch,
  SavedReportRead,
  ScatterView,
  TableView,
} from "../api/generated/types.gen";
import {
  zInsightValidationRequest,
  zSavedInsightCreate,
  zSavedInsightPatch,
  zSavedInsightRead,
  zSavedReportCreate,
  zSavedReportPatch,
  zSavedReportRead,
} from "../api/generated/zod.gen";

const generatedInsightDefinitionSchema = zInsightValidationRequest.omit({
  description: true,
  name: true,
  project_id: true,
});

const generatedReportDefinitionSchema = zSavedReportCreate.omit({
  project_id: true,
});

export type ResultScope = Omit<ApiResultScope, "selection"> & {
  analysis_type_ids: string[];
  method_ids: string[];
  method_versions: string[];
  run_ids: string[];
  statuses: string[];
  run_contract_ids: string[];
  selection: NonNullable<ApiResultScope["selection"]>;
};

export type AnalysisValue = Omit<
  ApiAnalysisValue,
  "aggregation" | "as" | "filters" | "label" | "scope"
> & {
  aggregation: NonNullable<ApiAnalysisValue["aggregation"]>;
  as?: string;
  filters: DraftInsightFilter[];
  label?: string;
  scope?: ResultScope;
};

export type DraftInsightFilter = Omit<InsightFilter, "operator" | "value"> & {
  operator: NonNullable<InsightFilter["operator"]>;
  value: InsightFilter["value"];
};

type DraftTableView = Omit<
  TableView,
  "hidden_values" | "kind" | "null_format" | "numeric_format" | "sorting"
> & {
  hidden_values: string[];
  kind: "table";
  null_format: string;
  numeric_format: NonNullable<TableView["numeric_format"]>;
  sorting: NonNullable<TableView["sorting"]>;
};
type DraftScatterView = MaterializedView<ScatterView>;
type DraftMetricView = Omit<MetricView, "hidden_values" | "thresholds"> & {
  hidden_values: string[];
  thresholds: NonNullable<MetricView["thresholds"]>;
};
type DraftHistogramView = Omit<
  HistogramView,
  "bins" | "colors" | "hidden_values"
> & {
  bins: number;
  colors: Record<string, string>;
  hidden_values: string[];
};
type DraftCategoryChartView = MaterializedView<CategoryChartView>;
type DraftBoxplotView = Omit<BoxplotView, "colors" | "hidden_values"> & {
  colors: Record<string, string>;
  hidden_values: string[];
};
type DraftHeatmapView = Omit<HeatmapView, "colors" | "hidden_values" | "tooltips"> & {
  colors: string[];
  hidden_values: string[];
  tooltips: string[];
};
type MaterializedView<T extends { colors?: unknown; hidden_values?: string[]; tooltips?: string[] }> =
  Omit<T, "colors" | "hidden_values" | "tooltips"> & {
    colors: Record<string, string>;
    hidden_values: string[];
    tooltips: string[];
  };

export type InsightView =
  | DraftTableView
  | DraftScatterView
  | DraftMetricView
  | DraftHistogramView
  | DraftCategoryChartView
  | DraftBoxplotView
  | DraftHeatmapView;

export type InsightDraft = {
  version: 1;
  analysis: {
    grain: NonNullable<z.input<typeof zInsightValidationRequest>["analysis"]["grain"]>;
    values: AnalysisValue[];
    filters: DraftInsightFilter[];
    match_by?: NonNullable<z.input<typeof zInsightValidationRequest>["analysis"]["match_by"]> | null;
    join?: "outer" | "inner" | null;
    limit: number;
    random: boolean;
  };
  view: InsightView;
};

export type ReportDefinition = {
  version: 1;
  name: string;
  description?: string | null;
  filters: DraftInsightFilter[];
  limit?: number | null;
  random?: boolean | null;
  layout: { columns: number; row_height: number };
  insights: ReportInsight[];
  refresh_policy: { mode: "manual" };
};

export { type ReportInsight };

export const insightDefinitionSchema = generatedInsightDefinitionSchema.transform(
  materializeInsightDraft,
);
export const reportDefinitionSchema = generatedReportDefinitionSchema.transform(
  materializeReportDraft,
);

/** Convert a generated saved resource into complete frontend builder state. */
export function savedInsightToDraft(value: SavedInsightRead): InsightDraft {
  const saved = zSavedInsightRead.parse(value);
  return insightDefinitionSchema.parse({
    version: saved.version,
    analysis: {
      ...saved.analysis,
      values: saved.analysis.values.map(normalizeDraftValue),
    },
    view: saved.view,
  });
}

/** Build a generated create payload without persisted/read-only metadata. */
export function insightDraftToCreate(
  draft: InsightDraft,
  metadata: Pick<SavedInsightCreate, "name" | "project_id"> &
    Partial<Pick<SavedInsightCreate, "description" | "insight_id">>,
): SavedInsightCreate {
  return zSavedInsightCreate.parse({ ...draft, ...metadata });
}

/** Build a generated patch payload without persisted/read-only metadata. */
export function insightDraftToPatch(
  draft: InsightDraft,
  metadata: Partial<Pick<SavedInsightPatch, "name" | "description">> = {},
): SavedInsightPatch {
  return zSavedInsightPatch.parse({ ...draft, ...metadata });
}

/** Convert a generated saved report into complete frontend builder state. */
export function savedReportToDraft(value: SavedReportRead): ReportDefinition {
  const saved = zSavedReportRead.parse(value);
  return reportDefinitionSchema.parse({
    version: saved.version,
    name: saved.name,
    description: saved.description,
    filters: saved.filters,
    limit: saved.limit,
    random: saved.random,
    layout: saved.layout,
    insights: saved.insights,
    refresh_policy: saved.refresh_policy,
  });
}

/** Build a generated report create payload from frontend builder state. */
export function reportDraftToCreate(
  draft: ReportDefinition,
  projectId: string,
): SavedReportCreate {
  return zSavedReportCreate.parse({ ...draft, project_id: projectId });
}

/** Build a generated report patch payload from frontend builder state. */
export function reportDraftToPatch(
  draft: Partial<ReportDefinition>,
): SavedReportPatch {
  return zSavedReportPatch.parse(draft);
}

/** Return bindings that define a view and cannot be hidden in draft controls. */
export function requiredViewBindingIds(view: InsightView): Set<string> {
  if (view.kind === "scatter") return new Set([view.x, view.y]);
  if (view.kind === "metric") return new Set([view.value]);
  if (view.kind === "heatmap") return new Set([view.x, view.y, view.value]);
  if ("category" in view && view.category) return new Set([view.category]);
  return new Set<string>();
}

function normalizeDraftValue(value: ApiAnalysisValue): AnalysisValue {
  const normalized = { ...value };
  if (normalized.as === null) delete normalized.as;
  if (normalized.label === null) delete normalized.label;
  if (normalized.scope === null) delete normalized.scope;
  return {
    ...normalized,
    aggregation: normalized.aggregation ?? "raw",
    filters: (normalized.filters ?? []).map(materializeFilter),
    scope: normalized.scope ? materializeScope(normalized.scope) : undefined,
  } as AnalysisValue;
}

function materializeScope(scope: ApiResultScope): ResultScope {
  return {
    ...scope,
    selection: scope.selection ?? "latest_successful_per_sample",
    analysis_type_ids: scope.analysis_type_ids ?? [],
    method_ids: scope.method_ids ?? [],
    method_versions: scope.method_versions ?? [],
    run_ids: scope.run_ids ?? [],
    statuses: scope.statuses ?? [],
    run_contract_ids: scope.run_contract_ids ?? [],
  };
}

function materializeFilter(filter: InsightFilter): DraftInsightFilter {
  return { ...filter, operator: filter.operator ?? "eq" };
}

function materializeInsightDraft(
  value: z.output<typeof generatedInsightDefinitionSchema>,
): InsightDraft {
  return {
    version: 1,
    analysis: {
      ...value.analysis,
      grain: value.analysis.grain ?? "sample",
      values: value.analysis.values.map(normalizeDraftValue),
      filters: (value.analysis.filters ?? []).map(materializeFilter),
      limit: value.analysis.limit ?? 1000,
      random: value.analysis.random ?? false,
    },
    view: materializeView(value.view),
  };
}

function materializeView(view: SavedInsightCreate["view"]): InsightView {
  if (view.kind === "table") {
    return {
      ...view,
      hidden_values: view.hidden_values ?? [],
      kind: "table",
      sorting: view.sorting ?? [],
      null_format: view.null_format ?? "—",
      numeric_format: view.numeric_format ?? {},
    } as InsightView;
  }
  if (view.kind === "metric") {
    return {
      ...view,
      hidden_values: view.hidden_values ?? [],
      thresholds: view.thresholds ?? [],
    } as InsightView;
  }
  if (view.kind === "heatmap") {
    return {
      ...view,
      hidden_values: view.hidden_values ?? [],
      colors: view.colors ?? [],
      tooltips: view.tooltips ?? [],
    } as InsightView;
  }
  if (view.kind === "boxplot") {
    return {
      ...view,
      hidden_values: view.hidden_values ?? [],
      colors: view.colors ?? {},
    } as InsightView;
  }
  if (view.kind === "histogram") {
    return {
      ...view,
      hidden_values: view.hidden_values ?? [],
      bins: view.bins ?? 20,
      colors: view.colors ?? {},
    } as InsightView;
  }
  return {
    ...view,
    hidden_values: view.hidden_values ?? [],
    colors: view.colors ?? {},
    tooltips: view.tooltips ?? [],
  } as InsightView;
}

function materializeReportDraft(
  value: z.output<typeof generatedReportDefinitionSchema>,
): ReportDefinition {
  return {
    ...value,
    filters: (value.filters ?? []).map(materializeFilter),
    layout: {
      columns: value.layout?.columns ?? 12,
      row_height: value.layout?.row_height ?? 64,
    },
    refresh_policy: { mode: value.refresh_policy?.mode ?? "manual" },
  };
}
