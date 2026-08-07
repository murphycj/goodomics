import type { ReportInsight } from "../../lib/insightSchemas";
import { isRecord } from "../../lib/valueUtils";

/** Reads placed insight references from a strict report configuration. */
export function readReportInsights(
  config: Record<string, unknown>,
): ReportInsight[] {
  const insights = Array.isArray(config.insights) ? config.insights : [];
  return insights
    .filter(isRecord)
    .map((insight, index) => {
      const layout = isRecord(insight.layout) ? insight.layout : {};
      return {
        id: String(insight.id ?? ""),
        layout: {
          x: Number(layout.x ?? (index % 2) * 6),
          y: Number(layout.y ?? Math.floor(index / 2) * 5),
          width: Number(layout.width ?? 6),
          height: Number(layout.height ?? 5),
        },
      };
    })
    .filter((insight) => insight.id);
}

export type { ReportInsight } from "../../lib/insightSchemas";
