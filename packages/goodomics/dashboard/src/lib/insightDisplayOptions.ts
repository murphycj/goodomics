export type DisplayOptions = {
  showValues: boolean;
  showTrendLines: boolean;
  showLegend: boolean;
  showAnnotations: boolean;
};

export const DEFAULT_DISPLAY_OPTIONS: DisplayOptions = {
  showValues: false,
  showTrendLines: false,
  showLegend: true,
  showAnnotations: false,
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
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
