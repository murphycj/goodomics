import { isRecord } from "../../lib/valueUtils";

/** Grid placement for a single insight inside a saved report config. */
export type ReportItem = {
  insight_id: string;
  x: number;
  y: number;
  w: number;
  h: number;
};

/** Reads report config items and fills missing grid coordinates with sane defaults. */
export function readReportItems(config: Record<string, unknown>): ReportItem[] {
  const items = Array.isArray(config.items) ? config.items : [];
  return items
    .filter(isRecord)
    .map((item, index) => ({
      insight_id: String(item.insight_id ?? ""),
      x: Number(item.x ?? (index % 2) * 6),
      y: Number(item.y ?? Math.floor(index / 2) * 5),
      w: Number(item.w ?? 6),
      h: Number(item.h ?? 5),
    }))
    .filter((item) => item.insight_id);
}
