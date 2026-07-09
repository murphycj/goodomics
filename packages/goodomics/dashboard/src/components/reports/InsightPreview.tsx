import { ArrowDown, ArrowUp, ChevronDown, Plus, Trash2 } from "lucide-react";
import ReactECharts from "echarts-for-react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  DataGrid,
  type Column,
  type RenderHeaderCellProps,
  type SortColumn,
  type SortDirection,
} from "react-data-grid";
import "react-data-grid/lib/styles.css";
import {
  CellPreviewPanel,
  CellValue,
  type CellPreview,
} from "../ui/CellValueInspector";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import { sortGridRows } from "../ui/DataGridShell";
import { CHART_COLORS } from "../../lib/chartColors";
import {
  readDisplayOptions,
  type DisplayOptions,
} from "../../lib/insightDisplayOptions";
import { cn } from "../../lib/utils";

type InsightResult = Record<string, unknown>;
type GridRow = Record<string, unknown> & { __rowId: string };

/** Renders an executed insight as an ECharts chart, metric tile, or data grid. */
export function InsightPreview({
  config,
  result,
  setupWarning,
  tableActions,
}: {
  config?: Record<string, unknown>;
  result: InsightResult | null | undefined;
  setupWarning?: string | null;
  tableActions?: {
    addLabel: string;
    emptyLabel?: string;
    onAddColumn: () => void;
  };
}) {
  // The server echoes visualization in the result. Fall back to table so unknown
  // or partial payloads still render as inspectable data.
  const visualization = typeof result?.visualization === "string" ? result.visualization : "table";
  if (!result) {
    return (
      <div className="relative grid h-full min-h-[220px] place-items-center text-sm text-[#657082]">
        {setupWarning ? (
          <SetupOverlay
            actionLabel={tableActions?.emptyLabel}
            message={setupWarning}
            onAction={tableActions?.onAddColumn}
          />
        ) : null}
        <span>Preview an insight to see results.</span>
      </div>
    );
  }
  if (["metric", "stat", "number"].includes(visualization)) {
    // Metric payloads are intentionally compact: one value plus an optional
    // label, displayed without ECharts.
    const metric = isRecord(result.metric) ? result.metric : {};
    return (
      <div className="grid h-full min-h-[180px] content-center gap-2">
        <div className="text-[2.4rem] font-semibold tracking-normal text-[#16784a]">
          {formatCell(metric.value)}
        </div>
        <div className="text-sm text-[#657082]">{formatCell(metric.label)}</div>
      </div>
    );
  }
  if (visualization === "table" || !isRecord(result.echarts_options)) {
    // Any non-chart result should remain usable. The grid path doubles as a
    // fallback when the server returns rows but no ECharts option.
    return <InsightTable result={result} tableActions={tableActions} />;
  }
  const option = normalizeEChartsOption({
    config,
    option: result.echarts_options,
    result,
    visualization,
  });
  return (
    <div className="relative h-full min-h-[260px] w-full">
      <ReactECharts
        className="h-full min-h-[260px] w-full"
        notMerge
        option={option}
        style={{ height: "100%", minHeight: 260, width: "100%" }}
      />
      {setupWarning ? (
        <SetupOverlay
          actionLabel={tableActions?.emptyLabel}
          message={setupWarning}
          onAction={tableActions?.onAddColumn}
        />
      ) : null}
    </div>
  );
}

function SetupOverlay({
  actionLabel,
  message,
  onAction,
}: {
  actionLabel?: string;
  message: string;
  onAction?: () => void;
}) {
  // Builder warnings are shown over the preview rather than replacing it so a
  // previously successful result can remain visible while settings are adjusted.
  return (
    <div className="absolute inset-0 z-10 grid place-items-center bg-white/78 backdrop-blur-[1px]">
      <div className="grid max-w-[360px] gap-3 rounded-md border border-[#f6c76d] bg-[#fff8e5] px-4 py-3 text-center text-sm font-medium text-[#8a5a00]">
        <span>{message}</span>
        {actionLabel && onAction ? (
          <button
            className="mx-auto inline-flex h-9 items-center justify-center rounded-md border border-[#16784a] bg-white px-3 text-sm font-semibold text-[#16784a] transition-colors hover:bg-[#edf8f2] focus:outline-none focus:ring-0"
            type="button"
            onClick={onAction}
          >
            {actionLabel}
          </button>
        ) : null}
      </div>
    </div>
  );
}

function normalizeEChartsOption({
  config,
  option,
  result,
  visualization,
}: {
  config?: Record<string, unknown>;
  option: Record<string, unknown>;
  result: InsightResult;
  visualization: string;
}) {
  // The server returns chart intent as ECharts options, but the dashboard owns
  // final presentation details such as stable colors, axis label placement, and
  // grid padding that must work inside the resizable preview panel.
  const colors = readColorMap(config) ?? readColorMap(result) ?? {};
  const displayOptions = readDisplayOptions(config, readDisplayOptions(result));
  const normalized: Record<string, unknown> =
    visualization === "histogram"
      ? normalizeHistogramOption(option, result, colors)
      : { ...option };
  normalized.xAxis = normalizeAxis(
    normalized.xAxis,
    56,
    displayOptions.xAxisLabel,
  );
  normalized.yAxis = normalizeAxis(
    normalized.yAxis,
    44,
    displayOptions.yAxisLabel,
    displayOptions.yAxisScale,
  );
  normalized.title = normalizeTitle(normalized.title);
  normalized.grid = {
    ...(isRecord(normalized.grid) ? normalized.grid : {}),
    left: 64,
    right: 32,
    top: displayOptions.showLegend ? 72 : 40,
    bottom: 96,
    containLabel: true,
  };
  normalized.legend = normalizeLegend(normalized.legend, displayOptions.showLegend);
  normalized.color = Array.isArray(normalized.color) ? normalized.color : CHART_COLORS;
  normalized.series = applySeriesOptions(
    applySeriesColors(normalized.series, colors),
    displayOptions,
    visualization,
  );
  return normalized;
}

function normalizeTitle(title: unknown) {
  // The dashboard cards already render insight titles above the chart. Hide
  // ECharts titles so legends and chart content do not collide with duplicate
  // headings inside the plot area.
  if (Array.isArray(title)) {
    return title.map((item) => (isRecord(item) ? { ...item, show: false } : item));
  }
  if (isRecord(title)) return { ...title, show: false };
  return title;
}

function normalizeAxis(
  axis: unknown,
  nameGap: number,
  label = "",
  scale: DisplayOptions["yAxisScale"] = "linear",
): unknown {
  // ECharts accepts either a single axis object or an array of axes. Normalize
  // both while preserving custom axis settings.
  if (Array.isArray(axis)) {
    return axis.map((item) => normalizeAxis(item, nameGap, label, scale));
  }
  if (!isRecord(axis)) return axis;
  const name = label.trim() || (typeof axis.name === "string" ? axis.name : "");
  const nextAxis = { ...axis };
  const axisType = typeof axis.type === "string" ? axis.type : "";
  const canUseNumericScale = !["category", "time"].includes(axisType);
  if (scale === "log" && canUseNumericScale) {
    nextAxis.type = "log";
    nextAxis.logBase = nextAxis.logBase ?? 10;
  } else if (axis.type === "log") {
    nextAxis.type = "value";
    delete nextAxis.logBase;
  }
  if (!name) return nextAxis;
  return {
    ...nextAxis,
    name,
    nameLocation: "middle",
    nameGap,
  };
}

function normalizeLegend(legend: unknown, show: boolean) {
  const base = isRecord(legend) ? legend : {};
  return {
    ...base,
    show,
    type: base.type ?? "scroll",
    top: base.top ?? 8,
    left: base.left ?? "center",
    right: base.right ?? 24,
  };
}

function applySeriesOptions(
  series: unknown,
  options: DisplayOptions,
  visualization: string,
) {
  if (!Array.isArray(series)) return series;
  return series.map((item) => {
    if (!isRecord(item)) return item;
    const supportsMarks = !["pie", "donut", "heatmap", "boxplot"].includes(
      visualization,
    );
    return {
      ...item,
      label: {
        ...(isRecord(item.label) ? item.label : {}),
        show: options.showValues,
      },
      markLine:
        options.showTrendLines && supportsMarks
          ? {
              ...(isRecord(item.markLine) ? item.markLine : {}),
              data: [{ type: "average", name: "Average" }],
            }
          : item.markLine,
      markPoint:
        options.showAnnotations && supportsMarks
          ? {
              ...(isRecord(item.markPoint) ? item.markPoint : {}),
              data: [
                { type: "max", name: "Max" },
                { type: "min", name: "Min" },
              ],
            }
          : item.markPoint,
    };
  });
}

function normalizeHistogramOption(
  option: Record<string, unknown>,
  result: InsightResult,
  colors: Record<string, string>,
) {
  // Histogram payloads may arrive as raw rows plus a generic option. Recompute
  // bins in the browser so previews stay correct when users switch fields before
  // a server-side option catches up.
  const xAxis = isRecord(option.xAxis) ? option.xAxis : {};
  const field = typeof xAxis.name === "string" ? xAxis.name : firstNumericColumn(result);
  const values = numericColumnValues(result, field);
  if (values.length === 0) {
    return { ...option };
  }
  const existingSeries = firstSeries(option.series);
  const existingData = Array.isArray(existingSeries?.data) ? existingSeries.data : [];
  const bins = histogramBins(values, existingData.length || 20);
  const color = colors[field] ?? colors[safeAlias(field)] ?? CHART_COLORS[0];
  return {
    ...option,
    tooltip: { trigger: "axis" },
    xAxis: {
      type: "value",
      name: field,
      nameLocation: "middle",
      nameGap: 48,
      scale: true,
      axisLabel: { formatter: "{value}" },
    },
    yAxis: {
      type: "value",
      name: "Count",
      nameLocation: "middle",
      nameGap: 44,
    },
    series: [
      {
        ...existingSeries,
        name: existingSeries?.name ?? "Count",
        type: "bar",
        data: bins.map((bin) => ({
          name: bin.label,
          value: [bin.center, bin.count],
        })),
        itemStyle: { ...(isRecord(existingSeries?.itemStyle) ? existingSeries.itemStyle : {}), color },
      },
    ],
  };
}

function applySeriesColors(series: unknown, colors: Record<string, string>) {
  // Series names can be field IDs, safe aliases, or user-entered labels. Try all
  // configured color keys before falling back to the Goodomics palette.
  if (!Array.isArray(series)) return series;
  const fallbackColors = uniqueValues(Object.values(colors));
  return series.map((item, index) => {
    if (!isRecord(item)) return item;
    if (item.type === "pie") return applyPieSliceColors(item, colors);
    const name = typeof item.name === "string" ? item.name : `series_${index + 1}`;
    const color = colors[name] ?? colors[safeAlias(name)] ?? fallbackColors[index] ?? CHART_COLORS[index % CHART_COLORS.length];
    return {
      ...item,
      itemStyle: { ...(isRecord(item.itemStyle) ? item.itemStyle : {}), color },
      lineStyle: { ...(isRecord(item.lineStyle) ? item.lineStyle : {}), color },
    };
  });
}

function applyPieSliceColors(item: Record<string, unknown>, colors: Record<string, string>) {
  // Pie charts need color at the slice datum level; putting a single color on
  // the series would make every slice identical.
  if (!Array.isArray(item.data)) return item;
  const seriesItem = { ...item };
  delete seriesItem.itemStyle;
  return {
    ...seriesItem,
    data: item.data.map((datum, index) => {
      const name = pieDatumName(datum);
      const color =
        (name ? colors[name] ?? colors[safeAlias(name)] : undefined) ??
        CHART_COLORS[index % CHART_COLORS.length];
      if (isRecord(datum)) {
        return {
          ...datum,
          itemStyle: { ...(isRecord(datum.itemStyle) ? datum.itemStyle : {}), color },
        };
      }
      return {
        name: name ?? String(datum),
        value: datum,
        itemStyle: { color },
      };
    }),
  };
}

function pieDatumName(datum: unknown) {
  // ECharts pie data can be object, tuple-like, or primitive depending on where
  // the option came from. Extract a stable label for color lookup.
  if (isRecord(datum) && typeof datum.name === "string") return datum.name;
  if (Array.isArray(datum) && datum.length > 0) return String(datum[0]);
  return typeof datum === "string" || typeof datum === "number" ? String(datum) : null;
}

function uniqueValues(values: string[]) {
  return Array.from(new Set(values));
}

function readColorMap(value: unknown) {
  // Color preferences are stored under display.colors in both saved configs and
  // some executed results.
  if (!isRecord(value) || !isRecord(value.display) || !isRecord(value.display.colors)) {
    return null;
  }
  return Object.fromEntries(
    Object.entries(value.display.colors)
      .filter((entry): entry is [string, string] => typeof entry[1] === "string")
      .map(([key, color]) => [key, color]),
  );
}

function firstSeries(series: unknown) {
  // Histogram normalization only needs the first usable series as a template.
  if (!Array.isArray(series)) return undefined;
  return series.find(isRecord);
}

function firstNumericColumn(result: InsightResult) {
  // If the option does not name a histogram field, infer one from returned rows.
  const rows = Array.isArray(result.rows) ? result.rows.filter(isRecord) : [];
  const columns = Array.isArray(result.columns) ? result.columns.map(String) : [];
  return columns.find((column) => rows.some((row) => typeof row[column] === "number")) ?? "";
}

function numericColumnValues(result: InsightResult, field: string) {
  // Keep binning strict: ignore missing, non-number, and non-finite values.
  const rows = Array.isArray(result.rows) ? result.rows.filter(isRecord) : [];
  return rows
    .map((row) => row[field])
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
}

function histogramBins(values: number[], binCount: number) {
  // Browser-side binning is intentionally simple and deterministic for preview
  // responsiveness; server-side export can still provide precomputed bins.
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  if (minimum === maximum) {
    return [{ start: minimum, end: maximum, center: minimum, label: formatBinEdge(minimum), count: values.length }];
  }
  const count = Math.min(Math.max(Math.trunc(binCount), 1), 100);
  const width = (maximum - minimum) / count;
  const counts = Array.from({ length: count }, () => 0);
  values.forEach((value) => {
    counts[Math.min(Math.trunc((value - minimum) / width), count - 1)] += 1;
  });
  return counts.map((bucketCount, index) => {
    const start = minimum + index * width;
    const end = minimum + (index + 1) * width;
    return {
      start,
      end,
      center: start + width / 2,
      label: `${formatBinEdge(start)}-${formatBinEdge(end)}`,
      count: bucketCount,
    };
  });
}

function formatBinEdge(value: number) {
  return Number.parseFloat(value.toPrecision(4)).toString();
}

function safeAlias(value: string) {
  // Match the alias convention used by the insight builder and server compiler.
  return value.replace(/[^a-zA-Z0-9_]+/g, "_").replace(/^_+|_+$/g, "").toLowerCase();
}

/** React Data Grid fallback for table insight results and non-chart payloads. */
function InsightTable({
  result,
  tableActions,
}: {
  result: InsightResult;
  tableActions?: {
    addLabel: string;
    emptyLabel?: string;
    onAddColumn: () => void;
  };
}) {
  const [sortColumns, setSortColumns] = useState<readonly SortColumn[]>([]);
  const [hiddenColumns, setHiddenColumns] = useState<Set<string>>(() => new Set());
  const [cellPreview, setCellPreview] = useState<CellPreview | null>(null);
  const [lastCellPreview, setLastCellPreview] = useState<CellPreview | null>(null);
  const cellPreviewPanelRef = useRef<HTMLElement | null>(null);
  // Rows from the server are plain objects. Add a synthetic row key for
  // react-data-grid without mutating the original result.
  const plotTable = isRecord(result.plot_table) ? result.plot_table : null;
  const columns = Array.isArray(plotTable?.columns)
    ? plotTable.columns.map(String)
    : Array.isArray(result.columns)
      ? result.columns.map(String)
      : [];
  const columnLabels = useMemo(
    () => ({
      ...readColumnLabels(result.column_labels),
      ...readColumnLabels(plotTable?.column_labels),
    }),
    [plotTable?.column_labels, result.column_labels],
  );
  const rawRows = Array.isArray(plotTable?.rows)
    ? plotTable.rows
    : Array.isArray(result.rows)
      ? result.rows
      : [];
  const visibleColumns = useMemo(
    () => columns.filter((column) => !hiddenColumns.has(column)),
    [columns, hiddenColumns],
  );
  const gridColumns = useMemo<Column<GridRow>[]>(
    () =>
      [
        ...visibleColumns.map((column) => ({
          key: column,
          name: columnLabels[column] ?? fallbackColumnLabel(column),
          minWidth: 120,
          resizable: true,
          sortable: true,
          renderHeaderCell: (props: RenderHeaderCellProps<GridRow>) => (
            <InsightColumnHeader
              label={columnLabels[column] ?? fallbackColumnLabel(column)}
              sortDirection={props.sortDirection}
              onRemove={() => {
                setHiddenColumns((current) => {
                  const next = new Set(current);
                  next.add(column);
                  return next;
                });
                setSortColumns((current) =>
                  current.filter((sortColumn) => sortColumn.columnKey !== column),
                );
                setCellPreview(null);
              }}
              onSortAscending={() =>
                setSortColumns([{ columnKey: column, direction: "ASC" }])
              }
              onSortDescending={() =>
                setSortColumns([{ columnKey: column, direction: "DESC" }])
              }
            />
          ),
          renderCell: ({ row }: { row: GridRow }) => <CellValue value={row[column]} />,
        })),
        ...(tableActions
          ? [
              {
                key: "__add_column",
                name: "",
                width: 56,
                resizable: false,
                renderHeaderCell: () => (
                  <button
                    aria-label={tableActions.addLabel}
                    className="grid h-8 w-8 place-items-center rounded-md border border-[#16784a] bg-[#e8f5ee] text-[#16784a] transition-colors hover:bg-[#d8efdf] hover:text-[#145c3a]"
                    type="button"
                    onClick={tableActions.onAddColumn}
                  >
                    <Plus className="h-4 w-4" />
                  </button>
                ),
                renderCell: () => null,
              } satisfies Column<GridRow>,
            ]
          : []),
      ],
    [columnLabels, tableActions, visibleColumns],
  );
  const rows = useMemo<GridRow[]>(
    () =>
      rawRows.filter(isRecord).map((row, index) => ({
        __rowId: String(index),
        ...row,
      })),
    [rawRows],
  );
  const sortedRows = useMemo(
    () => sortGridRows(rows, sortColumns),
    [rows, sortColumns],
  );
  useEffect(() => {
    setSortColumns([]);
    setHiddenColumns(new Set());
    setCellPreview(null);
    setLastCellPreview(null);
  }, [result]);
  useEffect(() => {
    if (cellPreview !== null) {
      setLastCellPreview(cellPreview);
    }
  }, [cellPreview]);
  useEffect(() => {
    if (cellPreview === null) return;
    function closePreviewOnOutsideClick(event: PointerEvent) {
      const target = event.target;
      if (
        target instanceof Node &&
        cellPreviewPanelRef.current !== null &&
        !cellPreviewPanelRef.current.contains(target)
      ) {
        setCellPreview(null);
      }
    }
    document.addEventListener("pointerdown", closePreviewOnOutsideClick);
    return () => {
      document.removeEventListener("pointerdown", closePreviewOnOutsideClick);
    };
  }, [cellPreview]);
  if (gridColumns.length === 0) {
    return (
      <div className="grid h-full min-h-[220px] place-items-center text-sm text-[#657082]">
        No rows returned.
      </div>
    );
  }
  return (
    <div className="flex h-full min-h-[260px] min-w-0 bg-white">
      <DataGrid
        className="goodomics-data-grid h-full min-w-0 flex-1"
        columns={gridColumns}
        defaultColumnOptions={{ resizable: true }}
        headerRowHeight={40}
        rowHeight={38}
        rowKeyGetter={(row: GridRow) => row.__rowId}
        rows={sortedRows}
        sortColumns={sortColumns}
        onCellDoubleClick={(args) => {
          if (args.column.key === "__add_column") return;
          const column = String(args.column.key);
          setCellPreview({
            column: columnLabels[column] ?? fallbackColumnLabel(column),
            rowNumber: Number(args.row.__rowId) + 1,
            tableName: "Insight table",
            value: args.row[column],
          });
        }}
        onSortColumnsChange={(nextSort) => {
          setSortColumns(nextSort.slice(-1));
          setCellPreview(null);
        }}
      />
      {cellPreview ? (
        <CellPreviewPanel
          isOpen
          panelRef={cellPreviewPanelRef}
          preview={cellPreview}
          onClose={() => setCellPreview(null)}
          onClosed={() => undefined}
        />
      ) : lastCellPreview ? (
        <CellPreviewPanel
          isOpen={false}
          panelRef={cellPreviewPanelRef}
          preview={lastCellPreview}
          onClose={() => setCellPreview(null)}
          onClosed={() => setLastCellPreview(null)}
        />
      ) : null}
    </div>
  );
}

function InsightColumnHeader({
  label,
  onRemove,
  onSortAscending,
  onSortDescending,
  sortDirection,
}: {
  label: string;
  onRemove: () => void;
  onSortAscending: () => void;
  onSortDescending: () => void;
  sortDirection: SortDirection | undefined;
}) {
  return (
    <div className="flex h-full w-full min-w-0 items-center gap-2">
      <span className="min-w-0 truncate">{label}</span>
      <div className="ml-auto flex shrink-0 items-center gap-1">
        {sortDirection ? <SortTriangle direction={sortDirection} /> : null}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              aria-label={`Column actions for ${label}`}
              className={cn(
                "grid h-7 w-7 shrink-0 place-items-center rounded-md text-[#657082] transition-colors hover:bg-[#eef3f7] hover:text-[#1d2430] focus:outline-none focus:ring-0",
                sortDirection && "bg-[#eef8f2] text-[#16784a]",
              )}
              type="button"
              onClick={(event) => event.stopPropagation()}
            >
              <ChevronDown className="h-4 w-4" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            align="end"
            className="min-w-[210px]"
            onClick={(event) => event.stopPropagation()}
          >
            <DropdownMenuItem onClick={onSortAscending}>
              <ArrowUp className="h-4 w-4 text-[#657082]" />
              Sort ascending
            </DropdownMenuItem>
            <DropdownMenuItem onClick={onSortDescending}>
              <ArrowDown className="h-4 w-4 text-[#657082]" />
              Sort descending
            </DropdownMenuItem>
            <DropdownMenuItem
              className="text-[#b42318] focus:bg-[#fff1f1] focus:text-[#9a1b16]"
              onClick={onRemove}
            >
              <Trash2 className="h-4 w-4" />
              Remove column
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}

function SortTriangle({ direction }: { direction: SortDirection }) {
  return (
    <span
      aria-label={direction === "ASC" ? "Sorted ascending" : "Sorted descending"}
      className={cn(
        "block h-0 w-0 shrink-0 border-x-[5px] border-x-transparent",
        direction === "ASC"
          ? "border-b-[7px] border-b-[#16784a]"
          : "border-t-[7px] border-t-[#16784a]",
      )}
      role="img"
    />
  );
}

function readColumnLabels(value: unknown) {
  if (!isRecord(value)) return {};
  return Object.fromEntries(
    Object.entries(value).filter((entry): entry is [string, string] => {
      const [, label] = entry;
      return typeof label === "string" && label.trim().length > 0;
    }),
  );
}

function fallbackColumnLabel(column: string) {
  const labels: Record<string, string> = {
    run_sample_id: "Run sample",
    sample_id: "Sample",
    run_id: "Run",
    entity_id: "Subject",
    feature_id: "Feature",
    source_file_id: "Source file",
  };
  return labels[column] ?? titleCase(column.replaceAll("_", " "));
}

function titleCase(value: string) {
  return value.replace(/\b\w/g, (match) => match.toUpperCase());
}

function formatCell(value: unknown) {
  // Keep table/metric display compact and predictable for mixed JSON payloads.
  if (value === null || value === undefined || value === "") return "NA";
  if (typeof value === "number") return Number.isInteger(value) ? value.toLocaleString() : value.toPrecision(4);
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
