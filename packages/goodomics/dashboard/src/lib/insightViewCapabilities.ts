import type { InsightView } from "./insightSchemas";
import {
  getInsightViewDefinition,
  type InsightViewCapability,
  type InsightViewKindWith,
} from "./insightViewCatalog";

type NarrowableCapability = Exclude<InsightViewCapability, "marks">;

type InsightViewWith<Capability extends NarrowableCapability> =
  Extract<InsightView, { kind: InsightViewKindWith<Capability> }>;

export type AxisView = InsightViewWith<"axes">;
export type CategoryBindingView = InsightViewWith<"categoryBinding">;
export type RecordColorView = InsightViewWith<"recordColors">;
export type TooltipView = InsightViewWith<"tooltips">;

function hasCapability(
  view: InsightView,
  capability: NarrowableCapability,
) {
  return getInsightViewDefinition(view.kind).capabilities[capability];
}

export function hasAxes(view: InsightView): view is AxisView {
  return hasCapability(view, "axes");
}

export function hasCategoryBinding(
  view: InsightView,
): view is CategoryBindingView {
  return hasCapability(view, "categoryBinding");
}

export function hasRecordColors(view: InsightView): view is RecordColorView {
  return hasCapability(view, "recordColors");
}

export function hasTooltips(view: InsightView): view is TooltipView {
  return hasCapability(view, "tooltips");
}
