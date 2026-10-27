/** Shared version 2 insight/report types and generated-contract adapters. */

import { z } from "zod";
import type {
  FieldSelection,
  ReportInsight,
  SavedInsightCreate,
  SavedInsightPatch,
  SavedInsightRead,
  SavedReportCreate,
  SavedReportPatch,
  SavedReportRead,
} from "../api/generated/types.gen";
import {
  zAlterationMatrixQuery,
  zAssociationQuery,
  zBoxplotView,
  zCategoryChartView,
  zDistributionQuery,
  zGenomeProfileQuery,
  zHeatmapView,
  zHistogramView,
  zInsightValidationRequest,
  zMatrixQuery,
  zMetricView,
  zRelationshipQuery,
  zRowsQuery,
  zSavedInsightRead,
  zSavedReportCreate,
  zSavedReportPatch,
  zSavedReportRead,
  zScatterView,
  zSeriesQuery,
  zSpecializedView,
  zSummaryQuery,
  zSurvivalQuery,
  zTableView,
  zTimelineQuery,
  zVariantPositionQuery,
} from "../api/generated/zod.gen";

export type QueryNode = SavedInsightCreate["query"];
export type InsightView = SavedInsightCreate["view"];
export type QueryKind = QueryNode["kind"];
export type ViewKind = InsightView["kind"];
export type { FieldSelection, ReportInsight };

export type InsightDraft = {
  version: 2;
  name: string;
  query: QueryNode;
  view: InsightView;
};

export type ReportDefinition = Pick<
  SavedReportCreate,
  | "version"
  | "name"
  | "description"
  | "filters"
  | "limit"
  | "random"
  | "layout"
  | "insights"
  | "refresh_policy"
>;

const queryNodeSchema = z.union([
  zRowsQuery,
  zSummaryQuery,
  zRelationshipQuery,
  zDistributionQuery,
  zSeriesQuery,
  zMatrixQuery,
  zAlterationMatrixQuery,
  zVariantPositionQuery,
  zGenomeProfileQuery,
  zSurvivalQuery,
  zTimelineQuery,
  zAssociationQuery,
]);

const insightViewSchema = z.union([
  zTableView,
  zScatterView,
  zMetricView,
  zHistogramView,
  zCategoryChartView,
  zBoxplotView,
  zHeatmapView,
  zSpecializedView,
]);

export const insightDefinitionSchema = zInsightValidationRequest
  .omit({ description: true, project_id: true })
  .extend({ query: queryNodeSchema, view: insightViewSchema });

/** Parse saved insight responses without generated optional-discriminator ambiguity. */
export const savedInsightReadSchema = zSavedInsightRead.extend({
  query: queryNodeSchema,
  view: insightViewSchema,
});

export const reportDefinitionSchema = zSavedReportCreate.omit({
  project_id: true,
});

/** Convert a generated saved resource into complete v2 builder state. */
export function savedInsightToDraft(value: SavedInsightRead): InsightDraft {
  const saved = savedInsightReadSchema.parse(value);
  return insightDefinitionSchema.parse({
    version: saved.version,
    name: saved.name,
    query: saved.query,
    view: saved.view,
  }) as InsightDraft;
}

/** Build a create payload tied to the exact successful preview. */
export function insightDraftToCreate(
  draft: InsightDraft,
  metadata: {
    project_id: string;
    preview_fingerprint: string;
    description?: string | null;
    insight_id?: string;
  },
): SavedInsightCreate {
  return { ...draft, ...metadata };
}

/** Build a generated patch payload without read-only metadata. */
export function insightDraftToPatch(
  draft: InsightDraft,
  metadata: Partial<
    Pick<SavedInsightPatch, "description" | "name" | "preview_fingerprint">
  > = {},
): SavedInsightPatch {
  return { ...draft, ...metadata };
}

/** Convert a generated saved report into builder state. */
export function savedReportToDraft(value: SavedReportRead): ReportDefinition {
  const saved = zSavedReportRead.parse(value);
  return reportDefinitionSchema.parse(saved) as ReportDefinition;
}

/** Build a generated report create payload from builder state. */
export function reportDraftToCreate(
  draft: ReportDefinition,
  projectId: string,
): SavedReportCreate {
  return zSavedReportCreate.parse({ ...draft, project_id: projectId });
}

/** Build a generated report patch payload from builder state. */
export function reportDraftToPatch(
  draft: Partial<ReportDefinition>,
): SavedReportPatch {
  return zSavedReportPatch.parse(draft);
}
