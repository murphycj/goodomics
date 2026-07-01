import ReactECharts from "echarts-for-react";
import { useMemo } from "react";
import { DataGrid, type Column } from "react-data-grid";
import "react-data-grid/lib/styles.css";

type InsightResult = Record<string, unknown>;
type GridRow = Record<string, unknown> & { __rowId: string };

/** Renders an executed insight as an ECharts chart, metric tile, or data grid. */
export function InsightPreview({ result }: { result: InsightResult | null | undefined }) {
  const visualization = typeof result?.visualization === "string" ? result.visualization : "table";
  if (!result) {
    return (
      <div className="grid h-full min-h-[220px] place-items-center text-sm text-[#657082]">
        Preview an insight to see results.
      </div>
    );
  }
  if (["metric", "stat", "number"].includes(visualization)) {
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
    return <InsightTable result={result} />;
  }
  return (
    <ReactECharts
      className="h-full min-h-[260px] w-full"
      notMerge
      option={result.echarts_options}
      style={{ height: "100%", minHeight: 260, width: "100%" }}
    />
  );
}

/** React Data Grid fallback for table insight results and non-chart payloads. */
function InsightTable({ result }: { result: InsightResult }) {
  const columns = Array.isArray(result.columns) ? result.columns.map(String) : [];
  const rawRows = Array.isArray(result.rows) ? result.rows : [];
  const gridColumns = useMemo<Column<GridRow>[]>(
    () =>
      columns.map((column) => ({
        key: column,
        name: column,
        minWidth: 120,
        resizable: true,
        renderCell: ({ row }) => <span className="truncate">{formatCell(row[column])}</span>,
      })),
    [columns],
  );
  const rows = useMemo<GridRow[]>(
    () =>
      rawRows.filter(isRecord).map((row, index) => ({
        __rowId: String(index),
        ...row,
      })),
    [rawRows],
  );
  if (gridColumns.length === 0) {
    return (
      <div className="grid h-full min-h-[220px] place-items-center text-sm text-[#657082]">
        No rows returned.
      </div>
    );
  }
  return (
    <DataGrid
      className="goodomics-data-grid h-full min-h-[260px]"
      columns={gridColumns}
      defaultColumnOptions={{ resizable: true }}
      headerRowHeight={40}
      rowHeight={38}
      rowKeyGetter={(row: GridRow) => row.__rowId}
      rows={rows}
    />
  );
}

function formatCell(value: unknown) {
  if (value === null || value === undefined || value === "") return "NA";
  if (typeof value === "number") return Number.isInteger(value) ? value.toLocaleString() : value.toPrecision(4);
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
