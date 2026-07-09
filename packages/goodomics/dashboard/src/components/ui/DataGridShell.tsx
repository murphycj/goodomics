import { ChevronDown, ChevronUp, Search } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import {
  DataGrid,
  type Column,
  type RenderHeaderCellProps,
  type SortColumn,
  type SortDirection,
} from "react-data-grid";
import "react-data-grid/lib/styles.css";
import { cn } from "../../lib/utils";
import { Input } from "./input";
import { ColumnVisibilityMenu } from "./ColumnVisibilityMenu";
import { PaginationBar } from "./PaginationBar";

export type GridColumnOption = {
  key: string;
  label: string;
};

/** Shared React Data Grid shell for dense project data browsers. */
export function DataGridShell<Row>({
  autoFocusSearch = false,
  columnOptions,
  columns,
  emptyMessage,
  error,
  hiddenColumns,
  isFetching = false,
  isLoading,
  itemLabel = "records",
  onHiddenColumnsChange,
  onPageChange,
  onPageSizeChange,
  onRowOpen,
  onSearchChange,
  pageIndex,
  pageSize,
  pageSizeOptions,
  rowKeyGetter,
  rows,
  searchPlaceholder,
  searchValue,
  selectionFirstColumn = false,
  sortValueGetter,
  toolbarActions,
  total,
}: {
  autoFocusSearch?: boolean;
  columnOptions?: GridColumnOption[];
  columns: Column<Row>[];
  emptyMessage: string;
  error?: Error | null;
  hiddenColumns?: Set<string>;
  isFetching?: boolean;
  isLoading: boolean;
  itemLabel?: string;
  onHiddenColumnsChange?: (hiddenColumns: Set<string>) => void;
  onPageChange: (pageIndex: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  onRowOpen?: (row: Row) => void;
  onSearchChange: (value: string) => void;
  pageIndex: number;
  pageSize: number;
  pageSizeOptions?: number[];
  rowKeyGetter: (row: Row) => string;
  rows: Row[];
  searchPlaceholder: string;
  searchValue: string;
  selectionFirstColumn?: boolean;
  sortValueGetter?: (row: Row, columnKey: string) => unknown;
  toolbarActions?: ReactNode;
  total: number;
}) {
  const searchInputRef = useRef<HTMLInputElement>(null);
  const [sortColumns, setSortColumns] = useState<readonly SortColumn[]>([]);
  const showColumnMenu =
    columnOptions && hiddenColumns && onHiddenColumnsChange;
  const sortableColumns = useMemo(
    () =>
      columns.map((column) => {
        const sortable = column.sortable ?? (column.key !== "selected");
        return {
          ...column,
          renderHeaderCell: sortable
            ? (props: RenderHeaderCellProps<Row>) => (
                <SortableHeaderCell
                  name={column.name}
                  sortDirection={props.sortDirection}
                />
              )
            : column.renderHeaderCell,
          sortable,
        };
      }),
    [columns],
  );
  const sortedRows = useMemo(
    () => sortGridRows(rows, sortColumns, sortValueGetter),
    [rows, sortColumns, sortValueGetter],
  );

  useEffect(() => {
    if (!autoFocusSearch) return;
    const frame = window.requestAnimationFrame(() => {
      searchInputRef.current?.focus();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [autoFocusSearch]);

  return (
    <div className="flex h-full min-h-0 flex-col bg-white">
      <div className="flex min-h-[52px] shrink-0 flex-wrap items-center justify-between gap-3 border-b border-[#dce3eb] px-4 py-2">
        <label className="relative min-w-[240px] flex-1 cursor-text md:max-w-[380px]">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#758195]" />
          <Input
            ref={searchInputRef}
            aria-label={searchPlaceholder}
            className="pl-9"
            placeholder={searchPlaceholder}
            value={searchValue}
            onChange={(event) => onSearchChange(event.target.value)}
          />
        </label>
        <div className="flex shrink-0 items-center gap-2">
          {toolbarActions}
          {showColumnMenu ? (
            <ColumnVisibilityMenu
              columns={columnOptions}
              hiddenColumns={hiddenColumns}
              onChange={onHiddenColumnsChange}
            />
          ) : null}
        </div>
      </div>
      <div className="min-h-0 flex-1">
        {isLoading ? (
          <GridMessage>Loading {itemLabel}...</GridMessage>
        ) : error ? (
          <GridMessage tone="error">{error.message}</GridMessage>
        ) : rows.length === 0 ? (
          <GridMessage>{emptyMessage}</GridMessage>
        ) : (
          <DataGrid
            className={cn(
              "goodomics-data-grid h-full",
              selectionFirstColumn &&
                "goodomics-data-grid--selection-first-column",
            )}
            columns={sortableColumns}
            headerRowHeight={42}
            rowClass={() => (onRowOpen ? "cursor-pointer" : "")}
            rowHeight={46}
            rowKeyGetter={rowKeyGetter}
            rows={sortedRows}
            sortColumns={sortColumns}
            onCellClick={onRowOpen ? ({ row }) => onRowOpen(row) : undefined}
            onSortColumnsChange={(nextSortColumns) =>
              setSortColumns(nextSortColumns.slice(-1))
            }
          />
        )}
      </div>
      <PaginationBar
        isLoading={isFetching}
        itemLabel={itemLabel}
        onPageChange={onPageChange}
        onPageSizeChange={onPageSizeChange}
        pageIndex={pageIndex}
        pageSize={pageSize}
        pageSizeOptions={pageSizeOptions}
        total={total}
      />
    </div>
  );
}

function SortableHeaderCell({
  name,
  sortDirection,
}: {
  name: ReactNode;
  sortDirection: SortDirection | undefined;
}) {
  return (
    <div className="flex w-full min-w-0 items-center gap-2">
      <span className="min-w-0 truncate">{name}</span>
      {sortDirection ? (
        <span className="ml-auto flex h-5 w-4 shrink-0 flex-col items-center justify-center leading-none">
          <ChevronUp
            aria-hidden="true"
            className={cn(
              "h-3 w-3",
              sortDirection === "ASC" ? "text-[#293241]" : "text-[#a6b1c0]",
            )}
            strokeWidth={2.4}
          />
          <ChevronDown
            aria-hidden="true"
            className={cn(
              "-mt-1 h-3 w-3",
              sortDirection === "DESC" ? "text-[#293241]" : "text-[#a6b1c0]",
            )}
            strokeWidth={2.4}
          />
        </span>
      ) : null}
    </div>
  );
}

export function sortGridRows<Row>(
  rows: Row[],
  sortColumns: readonly SortColumn[],
  sortValueGetter?: (row: Row, columnKey: string) => unknown,
) {
  if (sortColumns.length === 0) return rows;
  return rows
    .map((row, index) => ({ index, row }))
    .sort((a, b) => {
      for (const sortColumn of sortColumns) {
        const result = compareSortValues(
          getSortValue(a.row, sortColumn.columnKey, sortValueGetter),
          getSortValue(b.row, sortColumn.columnKey, sortValueGetter),
        );
        if (result !== 0) {
          return sortColumn.direction === "ASC" ? result : -result;
        }
      }
      return a.index - b.index;
    })
    .map(({ row }) => row);
}

function getSortValue<Row>(
  row: Row,
  columnKey: string,
  sortValueGetter?: (row: Row, columnKey: string) => unknown,
) {
  if (sortValueGetter) return sortValueGetter(row, columnKey);
  return (row as Record<string, unknown>)[columnKey];
}

function compareSortValues(left: unknown, right: unknown) {
  const leftMissing = left === null || left === undefined || left === "";
  const rightMissing = right === null || right === undefined || right === "";
  if (leftMissing && rightMissing) return 0;
  if (leftMissing) return 1;
  if (rightMissing) return -1;
  if (typeof left === "number" && typeof right === "number") {
    return left - right;
  }
  if (typeof left === "boolean" && typeof right === "boolean") {
    return Number(left) - Number(right);
  }
  return String(left).localeCompare(String(right), undefined, {
    numeric: true,
    sensitivity: "base",
  });
}

/** Centered loading, empty, or error message inside the grid canvas. */
function GridMessage({
  children,
  tone = "muted",
}: {
  children: ReactNode;
  tone?: "muted" | "error";
}) {
  return (
    <div
      className={`flex h-full items-center justify-center text-sm ${
        tone === "error" ? "text-[#b42318]" : "text-[#657082]"
      }`}
    >
      {children}
    </div>
  );
}
