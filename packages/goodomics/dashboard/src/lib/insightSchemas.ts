/*
 * Insight schema definitions for Goodomics dashboard.
 */

import { z } from "zod";
import {
  isMetadataFieldReference,
  parseFieldReference,
  valueReference,
} from "./fieldReferences";

const safeId = z.string().regex(/^[A-Za-z_][A-Za-z0-9_]*$/);
const grainSchema = z.enum([
  "sample",
  "subject",
  "run",
  "feature",
  "variant",
  "file",
]);

export const insightFilterSchema = z
  .object({
    field: z.string().min(1),
    operator: z
      .enum(["eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "contains"])
      .default("eq"),
    value: z.unknown(),
  })
  .strict();

export const resultScopeSchema = z
  .object({
    selection: z
      .enum([
        "latest_successful_per_sample",
        "all_eligible",
        "specific_methods",
        "specific_versions",
        "specific_runs",
        "pinned_results",
      ])
      .default("latest_successful_per_sample"),
    analysis_type_ids: z.array(z.string()).default([]),
    method_ids: z.array(z.string()).default([]),
    method_versions: z.array(z.string()).default([]),
    run_ids: z.array(z.string()).default([]),
    statuses: z.array(z.string()).default([]),
    started_after: z.string().nullable().optional(),
    ended_before: z.string().nullable().optional(),
    run_contract_ids: z.array(z.string()).default([]),
  })
  .strict();

export const analysisValueSchema = z
  .object({
    field: z
      .string()
      .min(1)
      .refine((value) => {
        try {
          parseFieldReference(value);
          return true;
        } catch {
          return false;
        }
      }, "Invalid field reference."),
    as: safeId.optional(),
    label: z.string().min(1).optional(),
    aggregation: z
      .enum(["raw", "count", "count_distinct", "sum", "avg", "min", "max"])
      .default("raw"),
    filters: z.array(insightFilterSchema).default([]),
    scope: resultScopeSchema.optional(),
  })
  .strict()
  .superRefine((value, context) => {
    if (isMetadataFieldReference(value.field) && value.scope) {
      context.addIssue({
        code: "custom",
        message: "Metadata values cannot define scope.",
      });
    }
  });

const numberFormatSchema = z
  .object({
    style: z
      .enum(["number", "percent", "scientific", "compact"])
      .default("number"),
    decimals: z.number().int().min(0).max(12).nullable().optional(),
    prefix: z.string().nullable().optional(),
    suffix: z.string().nullable().optional(),
  })
  .strict();

const axisSchema = z
  .object({
    label: z.string().nullable().optional(),
    scale: z.enum(["linear", "log", "category", "time"]).nullable().optional(),
    minimum: z.number().nullable().optional(),
    maximum: z.number().nullable().optional(),
  })
  .strict();

const colorsSchema = z.record(z.string(), z.string()).default({});
const hiddenValuesSchema = z.array(z.string().min(1)).default([]);
const tableViewSchema = z
  .object({
    kind: z.literal("table"),
    hidden_values: hiddenValuesSchema,
    sorting: z
      .array(
        z
          .object({
            by: z.string(),
            direction: z.enum(["asc", "desc"]).default("asc"),
          })
          .strict(),
      )
      .default([]),
    null_format: z.string().default("—"),
    numeric_format: z.record(z.string(), numberFormatSchema).default({}),
  })
  .strict();

const scatterViewSchema = z
  .object({
    kind: z.literal("scatter"),
    hidden_values: hiddenValuesSchema,
    x: z.string(),
    y: z.string(),
    x_axis: axisSchema.nullable().optional(),
    y_axis: axisSchema.nullable().optional(),
    colors: colorsSchema,
    tooltips: z.array(z.string()).default([]),
  })
  .strict();

const metricViewSchema = z
  .object({
    kind: z.literal("metric"),
    hidden_values: hiddenValuesSchema,
    value: z.string(),
    number_format: numberFormatSchema.nullable().optional(),
    thresholds: z
      .array(
        z
          .object({
            value: z.number(),
            label: z.string().nullable().optional(),
            color: z.string().nullable().optional(),
          })
          .strict(),
      )
      .default([]),
  })
  .strict();

const histogramViewSchema = z
  .object({
    kind: z.literal("histogram"),
    hidden_values: hiddenValuesSchema,
    bins: z.number().int().min(1).max(500).default(20),
    x_axis: axisSchema.nullable().optional(),
    y_axis: axisSchema.nullable().optional(),
    colors: colorsSchema,
  })
  .strict();

const categoryViewSchema = z
  .object({
    kind: z.enum(["bar", "stacked_bar", "line", "area", "pie", "donut"]),
    hidden_values: hiddenValuesSchema,
    category: z.string().nullable().optional(),
    x_axis: axisSchema.nullable().optional(),
    y_axis: axisSchema.nullable().optional(),
    colors: colorsSchema,
    tooltips: z.array(z.string()).default([]),
  })
  .strict();

const boxplotViewSchema = z
  .object({
    kind: z.literal("boxplot"),
    hidden_values: hiddenValuesSchema,
    category: z.string().nullable().optional(),
    x_axis: axisSchema.nullable().optional(),
    y_axis: axisSchema.nullable().optional(),
    colors: colorsSchema,
  })
  .strict();

const heatmapViewSchema = z
  .object({
    kind: z.literal("heatmap"),
    hidden_values: hiddenValuesSchema,
    x: z.string(),
    y: z.string(),
    value: z.string(),
    colors: z.array(z.string()).default([]),
    tooltips: z.array(z.string()).default([]),
  })
  .strict();

export const insightViewSchema = z.discriminatedUnion("kind", [
  tableViewSchema,
  scatterViewSchema,
  metricViewSchema,
  histogramViewSchema,
  categoryViewSchema,
  boxplotViewSchema,
  heatmapViewSchema,
]);

export const insightDefinitionSchema = z
  .object({
    version: z.literal(1),
    insight_id: z.string().optional(),
    name: z.string().optional(),
    description: z.string().nullable().optional(),
    analysis: z
      .object({
        grain: grainSchema.default("sample"),
        values: z.array(analysisValueSchema).min(1),
        filters: z.array(insightFilterSchema).default([]),
        match_by: grainSchema.nullable().optional(),
        join: z.enum(["outer", "inner"]).nullable().optional(),
        limit: z.number().int().min(1).max(10_000).default(1_000),
        random: z.boolean().default(false),
      })
      .strict(),
    view: insightViewSchema,
  })
  .strict()
  .superRefine((definition, context) => {
    const ids = definition.analysis.values.map(valueReference);
    if (new Set(ids).size !== ids.length) {
      context.addIssue({
        code: "custom",
        message:
          "Value references must be unique; add 'as' to repeated fields.",
      });
    }
    if (ids.includes(`${definition.analysis.grain}_id`)) {
      context.addIssue({
        code: "custom",
        message: "Value aliases cannot collide with the grain identity.",
      });
    }
    const hidden = definition.view.hidden_values;
    if (new Set(hidden).size !== hidden.length) {
      context.addIssue({
        code: "custom",
        message: "Hidden value references must be unique.",
      });
    }
    const unknownHidden = hidden.filter((id) => !ids.includes(id));
    if (unknownHidden.length) {
      context.addIssue({
        code: "custom",
        message: `Only analysis values can be hidden: ${unknownHidden.join(", ")}.`,
      });
    }
    const required = requiredViewBindingIds(definition.view);
    const hiddenRequired = hidden.filter((id) => required.has(id));
    if (hiddenRequired.length) {
      context.addIssue({
        code: "custom",
        message: `Required view bindings cannot be hidden: ${hiddenRequired.join(", ")}.`,
      });
    }
    const allowed = new Set([...ids, `${definition.analysis.grain}_id`]);
    const unknownReferences = viewReferences(definition.view).filter(
      (id) => !allowed.has(id),
    );
    if (unknownReferences.length) {
      context.addIssue({
        code: "custom",
        message: `View references unknown values: ${unknownReferences.join(", ")}.`,
      });
    }
    const category =
      "category" in definition.view ? definition.view.category : undefined;
    const visible = ids.filter((id) => !hidden.includes(id) && id !== category);
    if (
      ("bins" in definition.view || "category" in definition.view) &&
      !visible.length
    ) {
      context.addIssue({
        code: "custom",
        message: "The view requires a visible value.",
      });
    }
    if (
      ["pie", "donut"].includes(definition.view.kind) &&
      visible.length !== 1
    ) {
      context.addIssue({
        code: "custom",
        message: "Pie and donut views require exactly one visible value.",
      });
    }
    if (definition.view.kind === "stacked_bar" && visible.length < 2) {
      context.addIssue({
        code: "custom",
        message: "Stacked bars require at least two visible values.",
      });
    }
  });

export function requiredViewBindingIds(
  view: z.infer<typeof insightViewSchema>,
) {
  if (view.kind === "scatter") return new Set([view.x, view.y]);
  if (view.kind === "metric") return new Set([view.value]);
  if (view.kind === "heatmap") return new Set([view.x, view.y, view.value]);
  if ("category" in view && view.category) return new Set([view.category]);
  return new Set<string>();
}

function viewReferences(view: z.infer<typeof insightViewSchema>) {
  const references = [...view.hidden_values];
  if (view.kind === "table") {
    references.push(
      ...view.sorting.map((sort) => sort.by),
      ...Object.keys(view.numeric_format),
    );
  } else if (view.kind === "scatter") {
    references.push(
      view.x,
      view.y,
      ...view.tooltips,
      ...Object.keys(view.colors),
    );
  } else if (view.kind === "metric") {
    references.push(view.value);
  } else if (view.kind === "histogram") {
    references.push(...Object.keys(view.colors));
  } else if (view.kind === "heatmap") {
    references.push(view.x, view.y, view.value, ...view.tooltips);
  } else {
    if (view.category) references.push(view.category);
    references.push(...Object.keys(view.colors));
    if ("tooltips" in view) references.push(...view.tooltips);
  }
  return [...new Set(references)];
}

const reportInsightLayoutSchema = z
  .object({
    x: z.number().int().min(0),
    y: z.number().int().min(0),
    width: z.number().int().positive(),
    height: z.number().int().positive(),
  })
  .strict();

const reportInsightSchema = z
  .object({
    id: z.string().min(1),
    layout: reportInsightLayoutSchema,
  })
  .strict();

export const reportDefinitionShape = {
  version: z.literal(1),
  name: z.string().trim().min(1),
  description: z.string().nullable().optional(),
  filters: z.array(insightFilterSchema).default([]),
  limit: z.number().int().min(1).max(10_000).nullable().optional(),
  random: z.boolean().nullable().optional(),
  layout: z
    .object({
      columns: z.number().int().min(1).max(48).default(12),
      row_height: z.number().int().min(1).max(1_000).default(64),
    })
    .strict(),
  insights: z.array(reportInsightSchema).min(1),
  refresh_policy: z
    .object({ mode: z.literal("manual").default("manual") })
    .strict(),
};

export const reportDefinitionSchema = z
  .object(reportDefinitionShape)
  .strict()
  .superRefine((definition, context) => {
    const ids = definition.insights.map((insight) => insight.id);
    ids.forEach((id, index) => {
      if (ids.indexOf(id) !== index) {
        context.addIssue({
          code: "custom",
          message: `Report insight ids must be unique: ${id}.`,
          path: ["insights", index, "id"],
        });
      }
    });
  });

export type AnalysisValue = z.infer<typeof analysisValueSchema>;
export type InsightDraft = z.infer<typeof insightDefinitionSchema>;
export type InsightView = z.infer<typeof insightViewSchema>;
export type ReportDefinition = z.infer<typeof reportDefinitionSchema>;
export type ReportInsight = z.infer<typeof reportInsightSchema>;
export type ResultScope = z.infer<typeof resultScopeSchema>;
