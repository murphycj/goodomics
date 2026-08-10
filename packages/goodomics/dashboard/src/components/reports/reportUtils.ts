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

/** Applies react-grid-layout geometry to the portable saved-report model. */
export function applyReportGridLayout(
  insights: ReportInsight[],
  layout: ReadonlyArray<{
    i: string;
    x: number;
    y: number;
    w: number;
    h: number;
  }>,
): ReportInsight[] {
  const layoutById = new Map(layout.map((item) => [item.i, item]));
  return insights.map((insight) => {
    const next = layoutById.get(insight.id);
    if (!next) return insight;
    if (
      insight.layout.x === next.x &&
      insight.layout.y === next.y &&
      insight.layout.width === next.w &&
      insight.layout.height === next.h
    ) {
      return insight;
    }
    return {
      ...insight,
      layout: {
        x: next.x,
        y: next.y,
        width: next.w,
        height: next.h,
      },
    };
  });
}

/** Compares only the persisted insight placement fields. */
export function reportGridLayoutsEqual(
  left: ReportInsight[],
  right: ReportInsight[],
) {
  if (left.length !== right.length) return false;
  return left.every((insight, index) => {
    const candidate = right[index];
    return (
      candidate?.id === insight.id &&
      candidate.layout.x === insight.layout.x &&
      candidate.layout.y === insight.layout.y &&
      candidate.layout.width === insight.layout.width &&
      candidate.layout.height === insight.layout.height
    );
  });
}

/** Captures an immutable report-layout baseline for cancelable edit sessions. */
export function snapshotReportInsights(insights: ReportInsight[]) {
  return insights.map((insight) => ({
    ...insight,
    layout: { ...insight.layout },
  }));
}

export type { ReportInsight } from "../../lib/insightSchemas";
