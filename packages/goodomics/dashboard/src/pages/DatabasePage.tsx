import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { Database, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { DataGrid, type Column, type SortColumn } from "react-data-grid";
import "react-data-grid/lib/styles.css";
import {
  type DatabaseTable,
  getProjectDatabaseSummary,
  listProjectDatabaseTables,
  previewProjectDatabaseTable,
} from "../api";
import {
  AsyncBlock,
  Badge,
  Card,
  CardContent,
  ColumnVisibilityMenu,
  Input,
  PaginationBar,
} from "../components/ui";
import { cn, formatBytes } from "../lib/utils";

type TableStore = DatabaseTable["store"];
type GridRow = Record<string, unknown> & { __rowId: string };

const PAGE_SIZES = [25, 50, 100, 250];
const STORE_LABELS: Record<TableStore, string> = {
  catalog: "Catalog tables",
  analytics: "Analytical tables",
};

export function DatabasePage({ projectId }: { projectId: string }) {
  const [selected, setSelected] = useState<{ store: TableStore; name: string } | null>(
    null,
  );
  const [tableFilter, setTableFilter] = useState("");
  const [pageSize, setPageSize] = useState(100);
  const [offset, setOffset] = useState(0);
  const [sortColumns, setSortColumns] = useState<readonly SortColumn[]>([]);
  const [hiddenColumns, setHiddenColumns] = useState<Set<string>>(new Set());

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
    const firstPopulated = tables.find((table) => table.rows > 0) ?? tables[0];
    setSelected({ store: firstPopulated.store, name: firstPopulated.name });
  }, [selected, tables]);

  useEffect(() => {
    setOffset(0);
    setSortColumns([]);
    setHiddenColumns(new Set());
  }, [selected?.store, selected?.name]);

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
  const columns = useMemo<Column<GridRow>[]>(
    () =>
      (page?.columns ?? selectedTable?.columns ?? [])
        .filter((column) => !hiddenColumns.has(column))
        .map((column) => ({
          key: column,
          name: column,
          minWidth: column === "metadata_json" || column.endsWith("_json") ? 240 : 150,
          resizable: true,
          sortable: true,
          renderCell: ({ row }) => <CellValue value={row[column]} />,
        })),
    [hiddenColumns, page?.columns, selectedTable?.columns],
  );
  const rows = useMemo<GridRow[]>(
    () =>
      (page?.rows ?? []).map((row, index) => ({
        __rowId: `${offset + index}`,
        ...row,
      })),
    [offset, page?.rows],
  );
  const total = page?.total ?? selectedTable?.rows ?? 0;
  const pageIndex = Math.floor(offset / pageSize);

  return (
    <div className="grid h-[calc(100vh-48px)] min-h-0 grid-cols-1 overflow-hidden lg:grid-cols-[280px_minmax(0,1fr)]">
      <aside className="flex min-h-0 flex-col border-r border-[#dce3eb] pr-3">
        <div className="shrink-0 pb-3">
          <h1 className="m-0 truncate text-[1.75rem] font-semibold tracking-normal text-[#1d2430]">
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
            <div className="flex min-h-[34px] items-center justify-between gap-2 border-b border-[#dce3eb] px-3 py-1">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <Database className="h-4 w-4 shrink-0 text-[#21a66a]" />
                  <h2 className="m-0 truncate text-sm font-semibold">
                    {selectedTable?.name ?? "Select a table"}
                  </h2>
                  {selectedTable ? (
                    <Badge variant="outline">{STORE_LABELS[selectedTable.store]}</Badge>
                  ) : null}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <ColumnVisibilityMenu
                  columns={page?.columns ?? selectedTable?.columns ?? []}
                  hiddenColumns={hiddenColumns}
                  onChange={setHiddenColumns}
                />
              </div>
            </div>

            <div className="min-h-0 flex-1 bg-white">
              {selectedTable ? (
                <DataGrid
                  className="goodomics-data-grid h-full"
                  columns={columns}
                  rows={rows}
                  rowKeyGetter={(row) => row.__rowId}
                  sortColumns={sortColumns}
                  onSortColumnsChange={(nextSort) => {
                    setSortColumns(nextSort.slice(-1));
                    setOffset(0);
                  }}
                  defaultColumnOptions={{ resizable: true, sortable: true }}
                  rowHeight={42}
                  headerRowHeight={42}
                />
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-[#657082]">
                  No table selected.
                </div>
              )}
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
