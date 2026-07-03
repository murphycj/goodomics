import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { DataGrid, type Column } from "react-data-grid";
import "react-data-grid/lib/styles.css";
import type { SampleListItem } from "../api";
import { listProjectSamples } from "../api";
import {
  Card,
  CardContent,
  ColumnVisibilityMenu,
  PaginationBar,
} from "../components/ui";
import { formatDate } from "../lib/utils";

const SAMPLES_PAGE_SIZE = 50;
const SAMPLES_PAGE_SIZE_OPTIONS = [25, 50, 100, 250];
const SAMPLE_COLUMN_OPTIONS = [
  { key: "sample", label: "Sample" },
  { key: "subject_id", label: "Subject" },
  { key: "latest_run", label: "Latest run" },
  { key: "latest_run_created_at", label: "Latest activity" },
  { key: "run_count", label: "Runs" },
];

type SampleGridRow = SampleListItem & { __rowId: string };

/** Full-height sample browser for a project. */
export function ProjectSamplesPage({ projectId }: { projectId: string }) {
  return (
    <div className="flex h-[calc(100vh-48px)] min-h-0 flex-col overflow-hidden">
      <SamplesPanel projectId={projectId} />
    </div>
  );
}

/** Owns sample table state such as pagination and column visibility. */
function SamplesPanel({ projectId }: { projectId: string }) {
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(SAMPLES_PAGE_SIZE);
  const [hiddenColumns, setHiddenColumns] = useState<Set<string>>(new Set());
  const offset = page * pageSize;
  const samples = useQuery({
    queryKey: ["project-samples", projectId, offset, pageSize],
    queryFn: () => listProjectSamples({ projectId, limit: pageSize, offset }),
    placeholderData: (previous) => previous,
  });
  const data = samples.data;
  const rows = useMemo<SampleGridRow[]>(
    () =>
      (data?.items ?? []).map((sample) => ({
        __rowId: sample.sample_id,
        ...sample,
      })),
    [data?.items],
  );

  return (
    <Card className="mt-0 min-h-0 flex-1 overflow-hidden rounded-none border-x-0 p-0">
      <CardContent className="flex h-full min-h-0 flex-col">
        <div className="flex min-h-[42px] shrink-0 items-center justify-between gap-3 border-b border-[#dce3eb] bg-white px-4 py-2">
          <h1 className="m-0 truncate text-lg font-semibold tracking-normal text-[#1d2430]">
            Samples
          </h1>
          <ColumnVisibilityMenu
            columns={SAMPLE_COLUMN_OPTIONS}
            hiddenColumns={hiddenColumns}
            onChange={setHiddenColumns}
          />
        </div>
        <div className="min-h-0 flex-1 bg-white">
          {samples.isLoading ? (
            <GridMessage>Loading samples...</GridMessage>
          ) : samples.error ? (
            <GridMessage tone="error">{samples.error.message}</GridMessage>
          ) : rows.length === 0 ? (
            <GridMessage>No samples have been stored for this project yet.</GridMessage>
          ) : (
            <SamplesGrid
              hiddenColumns={hiddenColumns}
              projectId={projectId}
              samples={rows}
            />
          )}
        </div>
        <PaginationBar
          isLoading={samples.isFetching}
          itemLabel="records"
          onPageChange={setPage}
          onPageSizeChange={(nextPageSize) => {
            setPageSize(nextPageSize);
            setPage(0);
          }}
          pageIndex={page}
          pageSize={data?.limit ?? pageSize}
          pageSizeOptions={SAMPLES_PAGE_SIZE_OPTIONS}
          total={data?.total ?? 0}
        />
      </CardContent>
    </Card>
  );
}

/** React Data Grid view of samples with clickable rows. */
function SamplesGrid({
  hiddenColumns,
  projectId,
  samples,
}: {
  hiddenColumns: Set<string>;
  projectId: string;
  samples: SampleGridRow[];
}) {
  const navigate = useNavigate();
  const openSample = (sampleId: string) => {
    void navigate({
      to: "/project/$projectId/samples/$sampleId",
      params: { projectId, sampleId },
    });
  };
  const columns = useMemo<Column<SampleGridRow>[]>(
    () => {
      const allColumns: Column<SampleGridRow>[] = [
        {
          key: "sample",
          name: "Sample",
          minWidth: 260,
          resizable: true,
          renderCell: ({ row }) => (
            <span className="block w-full truncate text-left font-semibold">
              {row.sample_name ?? row.sample_id}
            </span>
          ),
        },
        {
          key: "subject_id",
          name: "Subject",
          minWidth: 180,
          resizable: true,
          renderCell: ({ row }) => <CellValue value={row.subject_id} />,
        },
        {
          key: "latest_run",
          name: "Latest run",
          minWidth: 240,
          resizable: true,
          renderCell: ({ row }) => (
            <CellValue value={row.latest_run_name ?? row.latest_run_id} />
          ),
        },
        {
          key: "latest_run_created_at",
          name: "Latest activity",
          minWidth: 190,
          resizable: true,
          renderCell: ({ row }) => (
            <CellValue
              value={
                row.latest_run_created_at
                  ? formatDate(row.latest_run_created_at)
                  : null
              }
            />
          ),
        },
        {
          key: "run_count",
          name: "Runs",
          minWidth: 110,
          resizable: true,
          renderCell: ({ row }) => (
            <span className="block w-full truncate text-left">
              {row.run_count.toLocaleString()}
            </span>
          ),
        },
      ];
      return allColumns.filter((column) => !hiddenColumns.has(column.key));
    },
    [hiddenColumns],
  );

  return (
    <DataGrid
      className="goodomics-data-grid h-full"
      columns={columns}
      rows={samples}
      rowClass={() => "cursor-pointer"}
      rowHeight={46}
      headerRowHeight={42}
      rowKeyGetter={(row) => row.__rowId}
      onCellClick={({ row }) => openSample(row.sample_id)}
    />
  );
}

/** Truncated cell renderer that normalizes missing sample values. */
function CellValue({ value }: { value?: string | null }) {
  return (
    <span className="block w-full truncate text-left text-[#253044]">
      {value || "—"}
    </span>
  );
}

/** Centered loading, empty, or error message inside the samples grid canvas. */
function GridMessage({
  children,
  tone = "muted",
}: {
  children: string;
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
