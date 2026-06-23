import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ExternalLink } from "lucide-react";
import { useMemo, useState } from "react";
import type { AnalyticsMetric, AnalyticsPayload, GoodomicsRun } from "../api";
import {
  fileContentUrl,
  getProjectRun,
  listProjectRunFiles,
  listProjectRunMetrics,
  listProjectRunPayloads,
} from "../api";
import {
  AsyncBlock,
  Detail,
  Page,
  SearchBox,
  SummaryTile,
} from "../components/ui";
import type { QueryState } from "../lib/types";
import {
  formatBytes,
  formatDate,
  formatMetricValue,
  shortPath,
  titleCase,
} from "../lib/utils";

export function RunDetailPage({
  projectId,
  runId,
}: {
  projectId: string;
  runId: string;
}) {
  const [tab, setTab] = useState<"overview" | "metrics" | "payloads" | "files">(
    "overview",
  );
  const run = useQuery({
    queryKey: ["project-run", projectId, runId],
    queryFn: () => getProjectRun(projectId, runId),
  });
  const metrics = useQuery({
    queryKey: ["project-run-metrics", projectId, runId],
    queryFn: () => listProjectRunMetrics(projectId, runId),
  });
  const payloads = useQuery({
    queryKey: ["project-run-payloads", projectId, runId],
    queryFn: () => listProjectRunPayloads(projectId, runId),
  });
  const files = useQuery({
    queryKey: ["project-run-files", projectId, runId],
    queryFn: () => listProjectRunFiles(projectId, runId),
  });

  return (
    <Page
      title={run.data?.name ?? runId}
      subtitle="Run-level metrics, payloads, and stored files."
    >
      <div className="topbar">
        <Link
          className="button secondary"
          to="/project/$projectId"
          params={{ projectId }}
        >
          Back to runs
        </Link>
        {files.data
          ?.filter((file) => file.kind === "multiqc_report")
          .slice(0, 1)
          .map((file) => (
            <a
              className="button"
              href={fileContentUrl(file, projectId)}
              key={file.id}
              rel="noreferrer"
              target="_blank"
            >
              <ExternalLink size={16} /> MultiQC report
            </a>
          ))}
      </div>
      <div className="tabs">
        {(["overview", "metrics", "payloads", "files"] as const).map((item) => (
          <button
            className={tab === item ? "active" : ""}
            key={item}
            onClick={() => setTab(item)}
            type="button"
          >
            {titleCase(item)}
          </button>
        ))}
      </div>
      {tab === "overview" && (
        <RunOverview
          files={files.data?.length ?? 0}
          metrics={metrics.data?.length ?? 0}
          payloads={payloads.data?.length ?? 0}
          query={run}
        />
      )}
      {tab === "metrics" && <MetricsTable query={metrics} />}
      {tab === "payloads" && <PayloadsTable query={payloads} />}
      {tab === "files" && <FilesTable projectId={projectId} query={files} />}
    </Page>
  );
}

function RunOverview({
  files,
  metrics,
  payloads,
  query,
}: {
  files: number;
  metrics: number;
  payloads: number;
  query: QueryState<GoodomicsRun>;
}) {
  return (
    <AsyncBlock query={query} empty="Run not found.">
      {(run) => (
        <>
          <div className="summary-grid">
            <SummaryTile label="Scalar metrics" value={metrics} />
            <SummaryTile label="Payloads" value={payloads} />
            <SummaryTile label="Files" value={files} />
            <SummaryTile label="Samples" value={run.samples.length} />
          </div>
          <div className="details-grid">
            <Detail label="Run ID" value={run.run_id} />
            <Detail label="Project ref" value={run.project_id ?? "—"} />
            <Detail label="Assay" value={run.assay ?? "—"} />
            <Detail label="Created" value={formatDate(run.created_at)} />
          </div>
        </>
      )}
    </AsyncBlock>
  );
}

function MetricsTable({ query }: { query: QueryState<AnalyticsMetric[]> }) {
  const [search, setSearch] = useState("");
  const filtered = useMemo(() => {
    const term = search.toLowerCase().trim();
    if (!query.data || !term) return query.data ?? [];
    return query.data.filter((metric) =>
      [
        metric.sample_key,
        metric.run_sample_key,
        metric.data_profile_key,
        metric.metric_key,
        metric.value,
        metric.source_file_id,
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(term)),
    );
  }, [query.data, search]);

  return (
    <AsyncBlock
      query={{ ...query, data: filtered }}
      empty="No scalar metrics were stored."
    >
      {(metrics) => (
        <>
          <SearchBox
            value={search}
            onChange={setSearch}
            placeholder="Filter metrics"
          />
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Sample</th>
                  <th>Profile</th>
                  <th>Metric</th>
                  <th>Value</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {metrics.map((metric, index) => (
                  <tr
                    key={`${metric.metric_key}-${metric.run_sample_key}-${index}`}
                  >
                    <td>{metric.sample_key ?? metric.run_sample_key ?? "—"}</td>
                    <td>{metric.data_profile_key}</td>
                    <td className="mono">{metric.metric_key}</td>
                    <td>{formatMetricValue(metric)}</td>
                    <td className="truncate">{metric.source_file_id ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </AsyncBlock>
  );
}

function PayloadsTable({ query }: { query: QueryState<AnalyticsPayload[]> }) {
  const [selected, setSelected] = useState<AnalyticsPayload | null>(null);
  return (
    <AsyncBlock query={query} empty="No table payloads were stored.">
      {(payloads) => (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Payload</th>
                  <th>Sample</th>
                  <th>Profile</th>
                  <th>Rows</th>
                  <th>Columns</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {payloads.map((payload) => (
                  <tr
                    key={`${payload.payload_name}-${payload.run_sample_key ?? "run"}`}
                  >
                    <td className="strong">{payload.payload_name}</td>
                    <td>{payload.run_sample_key ?? "—"}</td>
                    <td>{payload.data_profile_key}</td>
                    <td>{payload.row_count}</td>
                    <td>{payload.columns.length}</td>
                    <td className="right">
                      <button
                        className="button compact"
                        onClick={() => setSelected(payload)}
                        type="button"
                      >
                        View
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {selected && <PayloadPreview payload={selected} />}
        </>
      )}
    </AsyncBlock>
  );
}

function PayloadPreview({ payload }: { payload: AnalyticsPayload }) {
  const rows = payload.rows.slice(0, 25);
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h3>{payload.payload_name}</h3>
          <p>
            {payload.row_count} rows from{" "}
            {payload.source_file_id ?? "stored payload"}
          </p>
        </div>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {payload.columns.slice(0, 40).map((column) => (
                <th key={column}>{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index}>
                {payload.columns.slice(0, 40).map((column) => (
                  <td key={column}>{String(row[column] ?? "—")}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function FilesTable({
  projectId,
  query,
}: {
  projectId: string;
  query: QueryState<Awaited<ReturnType<typeof listProjectRunFiles>>>;
}) {
  return (
    <AsyncBlock query={query} empty="No files were stored.">
      {(files) => (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Kind</th>
                <th>Path</th>
                <th>Size</th>
                <th>SHA256</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {files.map((file) => (
                <tr key={file.id}>
                  <td>{file.kind}</td>
                  <td className="truncate">{shortPath(file.path)}</td>
                  <td>{formatBytes(file.size_bytes ?? 0)}</td>
                  <td className="mono">{file.sha256?.slice(0, 12) ?? "—"}</td>
                  <td className="right">
                    {file.kind.endsWith("report") && (
                      <a
                        className="button compact"
                        href={fileContentUrl(file, projectId)}
                        rel="noreferrer"
                        target="_blank"
                      >
                        <ExternalLink size={14} /> Open
                      </a>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </AsyncBlock>
  );
}
