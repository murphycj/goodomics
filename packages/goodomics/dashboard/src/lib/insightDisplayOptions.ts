export type DisplayOptions = {
  showValues: boolean;
  showTrendLines: boolean;
  showLegend: boolean;
  showAnnotations: boolean;
  xAxisLabel: string;
  yAxisLabel: string;
  yAxisScale: "linear" | "log";
};

export const DEFAULT_DISPLAY_OPTIONS: DisplayOptions = {
  showValues: false,
  showTrendLines: false,
  showLegend: true,
  showAnnotations: false,
  xAxisLabel: "",
  yAxisLabel: "",
  yAxisScale: "linear",
};

export const DISPLAY_OPTION_ITEMS: {
  key: keyof DisplayOptions;
  label: string;
}[] = [
  { key: "showValues", label: "Show values on series" },
  { key: "showTrendLines", label: "Show trend lines" },
  { key: "showLegend", label: "Show legend" },
  { key: "showAnnotations", label: "Show annotations" },
];

export function displayOptionsConfig(options: DisplayOptions) {
  return {
    show_values: options.showValues,
    show_trend_lines: options.showTrendLines,
    show_legend: options.showLegend,
    show_annotations: options.showAnnotations,
    x_axis_label: options.xAxisLabel.trim() || undefined,
    y_axis_label: options.yAxisLabel.trim() || undefined,
    y_axis_scale: options.yAxisScale,
  };
}

export function readDisplayOptions(
  value: unknown,
  fallback: DisplayOptions = DEFAULT_DISPLAY_OPTIONS,
): DisplayOptions {
  if (!isRecord(value) || !isRecord(value.display)) {
    return fallback;
  }
  return {
    showValues: Boolean(value.display.show_values ?? fallback.showValues),
    showTrendLines: Boolean(
      value.display.show_trend_lines ?? fallback.showTrendLines,
    ),
    showLegend: Boolean(value.display.show_legend ?? fallback.showLegend),
    showAnnotations: Boolean(
      value.display.show_annotations ?? fallback.showAnnotations,
    ),
    xAxisLabel: stringValue(value.display.x_axis_label, fallback.xAxisLabel),
    yAxisLabel: stringValue(value.display.y_axis_label, fallback.yAxisLabel),
    yAxisScale:
      value.display.y_axis_scale === "log" ? "log" : fallback.yAxisScale,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringValue(value: unknown, fallback: string) {
  return typeof value === "string" ? value : fallback;
}
