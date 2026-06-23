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
import { AsyncBlock, Page } from "../components/ui";
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
            <div className="panel muted">
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
    <div className="pagination">
      <span>
        {start.toLocaleString()}-{end.toLocaleString()} of{" "}
        {total.toLocaleString()} runs
      </span>
      <div className="pagination-actions">
        <button
          aria-label="First page"
          className="icon-button"
          disabled={!canGoBack}
          onClick={() => onPageChange(0)}
          title="First page"
          type="button"
        >
          <ChevronFirst size={18} />
        </button>
        <button
          aria-label="Previous page"
          className="icon-button"
          disabled={!canGoBack}
          onClick={() => onPageChange(Math.max(0, page - 1))}
          title="Previous page"
          type="button"
        >
          <ChevronLeft size={18} />
        </button>
        <span className="page-number">
          Page {(page + 1).toLocaleString()} of {pageCount.toLocaleString()}
        </span>
        <button
          aria-label="Next page"
          className="icon-button"
          disabled={!canGoForward}
          onClick={() => onPageChange(Math.min(pageCount - 1, page + 1))}
          title="Next page"
          type="button"
        >
          <ChevronRight size={18} />
        </button>
        <button
          aria-label="Last page"
          className="icon-button"
          disabled={!canGoForward}
          onClick={() => onPageChange(pageCount - 1)}
          title="Last page"
          type="button"
        >
          <ChevronLast size={18} />
        </button>
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
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Run</th>
            <th>Assay</th>
            <th>Status</th>
            <th>Created</th>
            <th>Samples</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr
              key={run.run_id}
              className="clickable-row"
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
              <td className="strong">{run.name ?? run.run_id}</td>
              <td>{run.assay ?? "—"}</td>
              <td>{run.status}</td>
              <td>{formatDate(run.created_at)}</td>
              <td>{run.samples.length}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
