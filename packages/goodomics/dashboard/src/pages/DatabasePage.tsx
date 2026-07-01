import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { ChevronDown, Copy, Database, Search, X } from "lucide-react";
import { type RefObject, useEffect, useMemo, useRef, useState } from "react";
import {
  DataGrid,
  SELECT_COLUMN_KEY,
  SelectColumn,
  type Column,
  type SortColumn,
} from "react-data-grid";
import "react-data-grid/lib/styles.css";
import {
  type DatabaseTable,
  getProjectDatabaseSummary,
  listProjectDatabaseTables,
  previewProjectDatabaseTable,
} from "../api";
import {
  AsyncBlock,
  Button,
  Card,
  CardContent,
  ColumnVisibilityMenu,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Input,
  PaginationBar,
} from "../components/ui";
import { writeClipboardText } from "../lib/clipboard";
import { showToast } from "../lib/toasts";
import { cn, formatBytes } from "../lib/utils";

type TableStore = DatabaseTable["store"];
type GridRow = Record<string, unknown> & { __rowId: string };
type CellPreview = {
  column: string;
  rowNumber: number;
  tableName: string;
  value: unknown;
};

const DEFAULT_COLUMN_WIDTH = 150;
const LONG_COLUMN_WIDTH = 220;
const PAGE_SIZES = [25, 50, 100, 250];
const STORE_LABELS: Record<TableStore, string> = {
  catalog: "Catalog tables",
  analytics: "Analytical tables",
};
const COPY_FORMAT_LABELS = {
  csv: "CSV",
  json: "JSON",
} as const;
type CopyFormat = keyof typeof COPY_FORMAT_LABELS;

/** Project database browser for catalog and analytical tables. */
export function DatabasePage({ projectId }: { projectId: string }) {
  const [selected, setSelected] = useState<{ store: TableStore; name: string } | null>(
    null,
  );
  const [tableFilter, setTableFilter] = useState("");
  const [pageSize, setPageSize] = useState(100);
  const [offset, setOffset] = useState(0);
  const [rowSearch, setRowSearch] = useState("");
  const [sortColumns, setSortColumns] = useState<readonly SortColumn[]>([]);
  const [hiddenColumns, setHiddenColumns] = useState<Set<string>>(new Set());
  const [selectedRows, setSelectedRows] = useState<ReadonlySet<string>>(
    () => new Set(),
  );
  const [cellPreview, setCellPreview] = useState<CellPreview | null>(null);
  const [lastCellPreview, setLastCellPreview] = useState<CellPreview | null>(null);
  const cellPreviewPanelRef = useRef<HTMLElement | null>(null);

  const summary = useQuery({
    queryKey: ["database-summary", projectId],
    queryFn: () => getProjectDatabaseSummary(projectId),
  });
  const tablesQuery = useQuery({
    queryKey: ["database-tables", projectId],
    queryFn: () => listProjectDatabaseTables(projectId),
  });

  const tables = tablesQuery.data ?? [];
  const selectedTable = useMemo(
    () =>
      selected
        ? tables.find(
            (table) => table.store === selected.store && table.name === selected.name,
          )
        : undefined,
    [selected, tables],
  );

  useEffect(() => {
    if (selected !== null || tables.length === 0) return;
    const params = new URLSearchParams(window.location.search);
    const requestedStore = params.get("store");
    const requestedTable = params.get("table");
    const requested = tables.find(
      (table) =>
        table.store === requestedStore && table.name === requestedTable,
    );
    const firstPopulated = requested ?? tables.find((table) => table.rows > 0) ?? tables[0];
    setSelected({ store: firstPopulated.store, name: firstPopulated.name });
  }, [selected, tables]);

  useEffect(() => {
    setOffset(0);
    setSortColumns([]);
    setHiddenColumns(new Set());
    setRowSearch("");
    setSelectedRows(new Set());
    setCellPreview(null);
  }, [selected?.store, selected?.name]);

  useEffect(() => {
    setSelectedRows(new Set());
    setCellPreview(null);
  }, [offset, pageSize]);

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

  const activeSort = sortColumns[0];
  const rowsQuery = useQuery({
    queryKey: [
      "database-table-preview",
      projectId,
      selected?.store,
      selected?.name,
      pageSize,
      offset,
      activeSort?.columnKey,
      activeSort?.direction,
    ],
    queryFn: () =>
      previewProjectDatabaseTable({
        projectId,
        store: selected?.store ?? "catalog",
        table: selected?.name ?? "",
        limit: pageSize,
        offset,
        sortBy: activeSort?.columnKey,
        sortDirection: activeSort?.direction.toLowerCase() as "asc" | "desc" | undefined,
      }),
    enabled: selected !== null,
    placeholderData: (previous) => previous,
  });

  const page = rowsQuery.data;
  const dataColumns = useMemo<Column<GridRow>[]>(
    () =>
      (page?.columns ?? selectedTable?.columns ?? [])
        .filter((column) => !hiddenColumns.has(column))
        .map((column) => ({
          key: column,
          name: column,
          width: defaultColumnWidth(column),
          minWidth: 120,
          resizable: true,
          sortable: true,
          renderCell: ({ row }) => <CellValue value={row[column]} />,
        })),
    [hiddenColumns, page?.columns, selectedTable?.columns],
  );
  const columns = useMemo<Column<GridRow>[]>(
    () => [SelectColumn as Column<GridRow>, ...dataColumns],
    [dataColumns],
  );
  const rows = useMemo<GridRow[]>(
    () =>
      (page?.rows ?? []).map((row, index) => ({
        __rowId: `${offset + index}`,
        ...row,
      })),
    [offset, page?.rows],
  );
  const searchedRows = useMemo(() => {
    const normalizedSearch = rowSearch.trim().toLowerCase();
    if (!normalizedSearch) return rows;
    return rows.filter((row) =>
      Object.entries(row).some(([key, value]) => {
        if (key === "__rowId" || value === null || value === undefined) return false;
        return stringifyCellForSearch(value).includes(normalizedSearch);
      }),
    );
  }, [rowSearch, rows]);
  const visibleRowIds = useMemo(
    () => new Set(searchedRows.map((row) => row.__rowId)),
    [searchedRows],
  );
  useEffect(() => {
    setSelectedRows((current) => {
      const next = new Set([...current].filter((rowId) => visibleRowIds.has(rowId)));
      return next.size === current.size ? current : next;
    });
  }, [visibleRowIds]);
  const selectedRowsInView = useMemo(
    () => searchedRows.filter((row) => selectedRows.has(row.__rowId)),
    [searchedRows, selectedRows],
  );
  const copyColumns = useMemo(
    () =>
      (page?.columns ?? selectedTable?.columns ?? []).filter(
        (column) => !hiddenColumns.has(column),
      ),
    [hiddenColumns, page?.columns, selectedTable?.columns],
  );
  const total = page?.total ?? selectedTable?.rows ?? 0;
  const pageIndex = Math.floor(offset / pageSize);

  const copySelection = async (format: CopyFormat) => {
    if (!selectedTable || selectedRowsInView.length === 0) return;
    try {
      await writeClipboardText(
        formatSelectedRows({
          columns: copyColumns,
          format,
          rows: selectedRowsInView,
        }),
      );
      showToast("database_rows_copied", {
        count: selectedRowsInView.length,
        format: COPY_FORMAT_LABELS[format],
      });
    } catch {
      showToast("database_rows_copy_failed", { tableName: selectedTable.name });
    }
  };

  return (
    <div className="grid h-[calc(100vh-48px)] min-h-0 grid-cols-1 overflow-hidden lg:grid-cols-[280px_minmax(0,1fr)]">
      <aside className="flex min-h-0 flex-col border-r border-[#dce3eb] pr-3">
        <div className="shrink-0 pb-3">
          <h1 className="m-0 truncate pl-3 text-[1.75rem] font-semibold tracking-normal text-[#1d2430]">
            Database
          </h1>
          <SummaryMetrics query={summary} />
        </div>

        <Card className="mt-0 min-h-0 flex-1 overflow-hidden p-0">
          <CardContent className="flex h-full min-h-0 flex-col bg-[#f8fafb] p-3">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#758195]" />
              <Input
                className="h-9 pl-9"
                placeholder="Search tables..."
                value={tableFilter}
                onChange={(event) => setTableFilter(event.target.value)}
              />
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto pr-1">
              <AsyncBlock query={tablesQuery} empty="No database tables available.">
                {(data) => (
                  <TableBrowser
                    tables={data}
                    selected={selected}
                    filter={tableFilter}
                    onSelect={(table) =>
                      setSelected({ store: table.store, name: table.name })
                    }
                  />
                )}
              </AsyncBlock>
            </div>
          </CardContent>
        </Card>
      </aside>

      <Card className="mt-0 min-h-0 overflow-hidden rounded-l-none border-l-0 p-0">
        <CardContent className="h-full min-h-0 overflow-hidden">
          <section className="flex h-full min-h-0 min-w-0 flex-col">
            <div className="flex min-h-[44px] items-center justify-between gap-3 border-b border-[#dce3eb] px-3 py-1.5">
              <div className="flex min-w-0 flex-1 items-center gap-2">
                <h2 className="m-0 inline-flex max-w-[34vw] shrink-0 items-center gap-2 truncate rounded-full border border-[#cfd8e3] bg-white px-3 py-1 text-sm font-semibold text-[#1d2430]">
                  <Database className="h-4 w-4 shrink-0 text-[#21a66a]" />
                  <span className="min-w-0 truncate">
                    {selectedTable?.name ?? "Select a table"}
                  </span>
                </h2>
                {selectedRowsInView.length > 0 ? (
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        className="h-8 shrink-0 rounded-md"
                        size="sm"
                        variant="outline"
                      >
                        <Copy className="h-3.5 w-3.5" />
                        Copy {selectedRowsInView.length.toLocaleString()} selected
                        <ChevronDown className="h-3.5 w-3.5" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="min-w-[180px]">
                      <DropdownMenuItem onClick={() => void copySelection("csv")}>
                        Copy as CSV
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={() => void copySelection("json")}>
                        Copy as JSON
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                ) : (
                  <div className="relative w-full max-w-[300px]">
                    <Search className="pointer-events-none absolute left-1 top-1/2 h-4 w-4 -translate-y-1/2 text-[#758195]" />
                    <Input
                      className="h-8 border-0 bg-transparent pl-7 pr-2 shadow-none focus-visible:ring-0"
                      placeholder="Search visible rows..."
                      value={rowSearch}
                      onChange={(event) => setRowSearch(event.target.value)}
                    />
                  </div>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <ColumnVisibilityMenu
                  columns={page?.columns ?? selectedTable?.columns ?? []}
                  hiddenColumns={hiddenColumns}
                  onChange={setHiddenColumns}
                />
              </div>
            </div>

            <div className="flex min-h-0 flex-1 bg-white">
              {selectedTable ? (
                <DataGrid
                  className="goodomics-data-grid h-full min-w-0 flex-1"
                  columns={columns}
                  rows={searchedRows}
                  rowKeyGetter={(row) => row.__rowId}
                  selectedRows={selectedRows}
                  onSelectedRowsChange={setSelectedRows}
                  sortColumns={sortColumns}
                  onSortColumnsChange={(nextSort) => {
                    setSortColumns(nextSort.slice(-1));
                    setOffset(0);
                    setSelectedRows(new Set());
                    setCellPreview(null);
                  }}
                  onCellDoubleClick={(args) => {
                    if (args.column.key === SELECT_COLUMN_KEY) return;
                    const column = args.column.key;
                    setCellPreview({
                      column,
                      rowNumber: offset + args.rowIdx + 1,
                      tableName: selectedTable.name,
                      value: args.row[column],
                    });
                  }}
                  defaultColumnOptions={{ resizable: true, sortable: true }}
                  rowHeight={42}
                  headerRowHeight={42}
                />
              ) : (
                <div className="flex h-full min-w-0 flex-1 items-center justify-center text-sm text-[#657082]">
                  No table selected.
                </div>
              )}
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

            <PaginationBar
              isLoading={rowsQuery.isFetching}
              onPageChange={(nextPageIndex) => setOffset(nextPageIndex * pageSize)}
              onPageSizeChange={(nextPageSize) => {
                setPageSize(nextPageSize);
                setOffset(0);
              }}
              pageIndex={pageIndex}
              pageSize={pageSize}
              pageSizeOptions={PAGE_SIZES}
              total={total}
            />
          </section>
        </CardContent>
      </Card>
    </div>
  );
}

function defaultColumnWidth(column: string) {
  const normalized = column.toLowerCase();
  if (
    normalized === "metadata_json" ||
    normalized.endsWith("_json") ||
    normalized.includes("description")
  ) {
    return LONG_COLUMN_WIDTH;
  }
  return DEFAULT_COLUMN_WIDTH;
}

/** Small storage summary panel for the database sidebar. */
function SummaryMetrics({
  query,
}: {
  query: UseQueryResult<Awaited<ReturnType<typeof getProjectDatabaseSummary>>>;
}) {
  if (query.isLoading) {
    return (
      <div className="mt-3 grid min-h-[48px] place-items-center rounded-lg border border-[#dce3eb] bg-white text-xs text-[#657082]">
        Loading database status...
      </div>
    );
  }
  if (query.error || !query.data) {
    return (
      <div className="mt-3 grid min-h-[48px] place-items-center rounded-lg border border-[#dce3eb] bg-white text-xs text-[#b42318]">
        Database status unavailable.
      </div>
    );
  }
  const metrics = [
    {
      label: "Database",
      subtitle: "SQLite catalog",
      value: formatBytes(query.data.sqlite_size_bytes),
    },
    {
      label: "Analytics database",
      subtitle: "DuckDB analytical store",
      value: formatBytes(query.data.duckdb_size_bytes),
    },
  ];
  return (
    <div className="mt-3 grid grid-cols-1 gap-2">
      {metrics.map((metric) => (
        <div
          className="min-w-0 rounded-lg border border-[#dce3eb] bg-white px-3 py-2 shadow-[0_10px_24px_rgb(25_32_43/0.04)]"
          key={metric.label}
        >
          <div className="flex items-start justify-between gap-2">
            <span className="min-w-0">
              <span className="block truncate text-[0.68rem] font-bold uppercase text-[#657082]">
                {metric.label}
              </span>
              <span className="mt-0.5 block truncate text-[0.7rem] text-[#7a8798]">
                {metric.subtitle}
              </span>
            </span>
            <strong className="shrink-0 text-sm tracking-normal text-[#1d2430]">
              {metric.value}
            </strong>
          </div>
        </div>
      ))}
    </div>
  );
}

/** Sidebar table navigator grouped by catalog and analytics stores. */
function TableBrowser({
  tables,
  selected,
  filter,
  onSelect,
}: {
  tables: DatabaseTable[];
  selected: { store: TableStore; name: string } | null;
  filter: string;
  onSelect: (table: DatabaseTable) => void;
}) {
  const normalizedFilter = filter.trim().toLowerCase();
  return (
    <div className="mt-4 space-y-4 pb-4">
      {(["catalog", "analytics"] as const).map((store) => {
        const filtered = tables.filter(
          (table) =>
            table.store === store &&
            (!normalizedFilter ||
              table.name.toLowerCase().includes(normalizedFilter)),
        );
        if (filtered.length === 0) return null;
        return (
          <div key={store}>
            <div className="mb-2 px-1 text-xs font-bold uppercase text-[#657082]">
              {STORE_LABELS[store]}
            </div>
            <div className="space-y-1">
              {filtered.map((table) => {
                const isSelected =
                  selected?.store === table.store && selected.name === table.name;
                return (
                  <button
                    key={`${table.store}:${table.name}`}
                    className={cn(
                      "flex h-9 w-full items-center justify-between gap-2 rounded-md px-2 text-left text-sm transition-colors",
                      isSelected
                        ? "bg-[#e8f8ef] text-[#12643f]"
                        : "text-[#293241] hover:bg-white",
                    )}
                    onClick={() => onSelect(table)}
                  >
                    <span className="min-w-0 truncate">{table.name}</span>
                    <span className="shrink-0 text-xs text-[#758195]">
                      {table.rows.toLocaleString()}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** Data grid cell renderer that preserves nulls, booleans, and structured values. */
function CellValue({ value }: { value: unknown }) {
  if (value === null || value === undefined) {
    return <span className="block w-full truncate text-left text-[#9aa5b5]">NULL</span>;
  }
  if (typeof value === "boolean") {
    return (
      <span className="block w-full truncate text-left">
        {value ? "TRUE" : "FALSE"}
      </span>
    );
  }
  if (typeof value === "object") {
    return (
      <code className="block w-full truncate text-left text-xs text-[#475569]">
        {JSON.stringify(value)}
      </code>
    );
  }
  return <span className="block w-full truncate text-left">{String(value)}</span>;
}

/** Slide-out panel for inspecting a full table cell value. */
function CellPreviewPanel({
  isOpen,
  onClosed,
  panelRef,
  preview,
  onClose,
}: {
  isOpen: boolean;
  onClosed: () => void;
  panelRef: RefObject<HTMLElement | null>;
  preview: CellPreview;
  onClose: () => void;
}) {
  const formattedValue = formatPreviewValue(preview.value);
  const lines = formattedValue.split("\n");
  return (
    <aside
      ref={panelRef}
      className={cn(
        "database-cell-preview-panel",
        isOpen
          ? "database-cell-preview-panel-open"
          : "database-cell-preview-panel-closed",
      )}
      onTransitionEnd={(event) => {
        if (event.propertyName === "width" && !isOpen) {
          onClosed();
        }
      }}
    >
      <div className="database-cell-preview-panel-inner">
        <div className="flex min-h-[48px] items-center justify-between gap-3 border-b border-[#dce3eb] px-4">
          <div className="min-w-0">
            <p className="m-0 truncate text-sm font-semibold text-[#1d2430]">
              Viewing value of: {preview.column}
            </p>
            <p className="m-0 mt-0.5 truncate text-xs text-[#657082]">
              {preview.tableName} · row {preview.rowNumber.toLocaleString()}
            </p>
          </div>
          <button
            aria-label="Close value preview"
            className="inline-flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-md border border-[#dce3eb] bg-white text-[#657082] transition-colors hover:border-[#8edeb4] hover:bg-[#eef8f2] hover:text-[#16784a] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#21a66a]"
            onClick={onClose}
            type="button"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto bg-[#1f2329] py-3">
          <div className="font-mono text-xs leading-5">
            {lines.map((line, index) => (
              <div
                className="grid grid-cols-[3rem_minmax(0,1fr)] px-3"
                key={`${index}:${line}`}
              >
                <span className="select-none pr-4 text-right text-[#7a8798]">
                  {index + 1}
                </span>
                <pre className="m-0 whitespace-pre-wrap break-words text-[#eef2f6]">
                  {line || " "}
                </pre>
              </div>
            ))}
          </div>
        </div>
      </div>
    </aside>
  );
}

function formatPreviewValue(value: unknown) {
  if (value === null || value === undefined) return "NULL";
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}

function stringifyCellForSearch(value: unknown) {
  return (typeof value === "object" ? JSON.stringify(value) : String(value))
    .toLowerCase()
    .trim();
}

function formatSelectedRows({
  columns,
  format,
  rows,
}: {
  columns: string[];
  format: CopyFormat;
  rows: GridRow[];
}) {
  const records = rows.map((row) => recordFromRow(row, columns));
  if (format === "json") {
    return JSON.stringify(records, null, 2);
  }
  return [
    columns.map(formatCsvCell).join(","),
    ...records.map((record) =>
      columns.map((column) => formatCsvCell(record[column])).join(","),
    ),
  ].join("\n");
}

function recordFromRow(row: GridRow, columns: string[]) {
  return Object.fromEntries(columns.map((column) => [column, row[column]]));
}

function formatCsvCell(value: unknown) {
  if (value === null || value === undefined) return "";
  const text = typeof value === "object" ? JSON.stringify(value) : String(value);
  if (/[",\n\r]/.test(text)) {
    return `"${text.replaceAll('"', '""')}"`;
  }
  return text;
}
