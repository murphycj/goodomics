import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import {
  ChevronFirst,
  ChevronLast,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { useState } from "react";
import type { GoodomicsRun } from "../api";
import { getProject, listProjectRuns } from "../api";
import {
  AsyncBlock,
  Button,
  Page,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableWrap,
} from "../components/ui";
import { formatDate } from "../lib/utils";

const RUNS_PAGE_SIZE = 50;

export function ProjectRunsPage({ projectId }: { projectId: string }) {
  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => getProject(projectId),
  });
  return (
    <Page
      title={project.data?.name ?? projectId}
      subtitle="Browse stored runs and inspect project QC context."
    >
      <RunsPanel projectId={projectId} />
    </Page>
  );
}

function RunsPanel({ projectId }: { projectId: string }) {
  const [page, setPage] = useState(0);
  const offset = page * RUNS_PAGE_SIZE;
  const runs = useQuery({
    queryKey: ["project-runs", projectId, offset, RUNS_PAGE_SIZE],
    queryFn: () =>
      listProjectRuns({ projectId, limit: RUNS_PAGE_SIZE, offset }),
  });
  return (
    <AsyncBlock
      query={runs}
      empty="No runs have been stored for this project yet."
    >
      {(data) => (
        <>
          {data.items.length === 0 ? (
            <div className="mt-4 rounded-lg border border-[#dce3eb] bg-white p-4 text-[#657082]">
              No runs have been stored for this project yet.
            </div>
          ) : (
            <RunsTable projectId={projectId} runs={data.items} />
          )}
          <PaginationControls
            isLoading={runs.isLoading}
            offset={data.offset}
            onPageChange={setPage}
            page={page}
            pageSize={data.limit}
            total={data.total}
          />
        </>
      )}
    </AsyncBlock>
  );
}

function PaginationControls({
  isLoading,
  offset,
  onPageChange,
  page,
  pageSize,
  total,
}: {
  isLoading: boolean;
  offset: number;
  onPageChange: (page: number) => void;
  page: number;
  pageSize: number;
  total: number;
}) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const start = total === 0 ? 0 : offset + 1;
  const end = Math.min(offset + pageSize, total);
  const canGoBack = page > 0 && !isLoading;
  const canGoForward = page + 1 < pageCount && !isLoading;

  return (
    <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-sm text-[#596678]">
      <span>
        {start.toLocaleString()}-{end.toLocaleString()} of {total.toLocaleString()} runs
      </span>
      <div className="flex flex-wrap items-center gap-1.5">
        <Button
          aria-label="First page"
          disabled={!canGoBack}
          onClick={() => onPageChange(0)}
          size="icon"
          title="First page"
          type="button"
          variant="outline"
        >
          <ChevronFirst size={18} />
        </Button>
        <Button
          aria-label="Previous page"
          disabled={!canGoBack}
          onClick={() => onPageChange(Math.max(0, page - 1))}
          size="icon"
          title="Previous page"
          type="button"
          variant="outline"
        >
          <ChevronLeft size={18} />
        </Button>
        <span className="min-w-[9.5rem] text-center text-[#1d2430]">
          Page {(page + 1).toLocaleString()} of {pageCount.toLocaleString()}
        </span>
        <Button
          aria-label="Next page"
          disabled={!canGoForward}
          onClick={() => onPageChange(Math.min(pageCount - 1, page + 1))}
          size="icon"
          title="Next page"
          type="button"
          variant="outline"
        >
          <ChevronRight size={18} />
        </Button>
        <Button
          aria-label="Last page"
          disabled={!canGoForward}
          onClick={() => onPageChange(pageCount - 1)}
          size="icon"
          title="Last page"
          type="button"
          variant="outline"
        >
          <ChevronLast size={18} />
        </Button>
      </div>
    </div>
  );
}

function RunsTable({
  projectId,
  runs,
}: {
  projectId: string;
  runs: GoodomicsRun[];
}) {
  const navigate = useNavigate();
  const openRun = (runId: string) => {
    void navigate({
      to: "/project/$projectId/runs/$runId",
      params: { projectId, runId },
    });
  };

  return (
    <TableWrap>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Run</TableHead>
            <TableHead>Assay</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Created</TableHead>
            <TableHead>Samples</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {runs.map((run) => (
            <TableRow
              key={run.run_id}
              className="cursor-pointer hover:!bg-[#eef8f2] focus-visible:outline-2 focus-visible:outline-[#8edeb4] focus-visible:outline-offset-[-2px]"
              onClick={() => openRun(run.run_id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  openRun(run.run_id);
                }
              }}
              role="link"
              tabIndex={0}
            >
              <TableCell className="font-bold">{run.name ?? run.run_id}</TableCell>
              <TableCell>{run.assay ?? "—"}</TableCell>
              <TableCell>{run.status}</TableCell>
              <TableCell>{formatDate(run.created_at)}</TableCell>
              <TableCell>{run.samples.length}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableWrap>
  );
}
