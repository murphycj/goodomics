/** Display helpers shared by saved-insight lists and result rendering. */

import { titleCase } from "./insightBuilder";

export function insightViewLabel(kind: string) {
  return titleCase(kind);
}

const INSIGHT_VIEW_ICON_FILES: Record<string, string> = {
  area: "area.png",
  association_matrix: "association-matrix.png",
  bar: "bar.png",
  boxplot: "boxplot.png",
  donut: "donut.png",
  genome_profile: "genome-profile.png",
  heatmap: "heatmap.png",
  histogram: "histogram.png",
  line: "line.png",
  lollipop: "lollipop.png",
  metric: "metric.png",
  oncoprint: "oncoprint.png",
  pie: "pie.png",
  scatter: "scatter.png",
  stacked_bar: "stacked-bar.png",
  survival: "survival.png",
  table: "table.png",
  timeline: "timeline.png",
  violin: "violin.png",
};

/** Return the stable public PNG for a saved insight view. */
export function insightViewIconPath(kind: string) {
  return `/plot-icons/${INSIGHT_VIEW_ICON_FILES[kind] ?? "fallback.png"}`;
}

export function insightViewSupportsMarks(kind: string) {
  return ["scatter", "bar", "stacked_bar", "line", "area", "histogram"].includes(kind);
}
