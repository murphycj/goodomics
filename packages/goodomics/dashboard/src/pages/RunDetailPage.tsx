import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ExternalLink } from "lucide-react";
import { useMemo, useState } from "react";
import type {
  AnalyticsMetric,
  AnalyticsPayload,
  GoodomicsRun,
  StoredFile,
} from "../api";
import {
  fileContentUrl,
  getProjectRun,
  listProjectRunFiles,
  listProjectRunMetrics,
  listProjectRunPayloads,
} from "../api";
import {
  AsyncBlock,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Detail,
  Page,
  SearchBox,
  SummaryTile,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableWrap,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../components/ui";
import type { QueryState } from "../lib/types";
import {
  formatBytes,
  formatDate,
  formatMetricValue,
  shortPath,
  titleCase,
} from "../lib/utils";

const tabs = ["overview", "metrics", "payloads", "files"] as const;

/** Run detail page with overview, metrics, payloads, and files. */
export function RunDetailPage({
  projectId,
  runId,
}: {
  projectId: string;
  runId: string;
}) {
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
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Button asChild variant="secondary">
          <Link to="/project/$projectId" params={{ projectId }}>
            Back to samples
          </Link>
        </Button>
        {files.data
          ?.filter((file) => file.kind === "multiqc_report")
          .slice(0, 1)
          .map((file) => (
            <Button asChild key={file.file_id}>
              <a
                href={fileContentUrl(file, projectId)}
                rel="noreferrer"
                target="_blank"
              >
                <ExternalLink size={16} /> MultiQC report
              </a>
            </Button>
          ))}
      </div>
      <Tabs className="w-full" defaultValue="overview">
        <TabsList>
          {tabs.map((item) => (
            <TabsTrigger key={item} value={item}>
              {titleCase(item)}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="overview">
          <RunOverview
            files={files.data?.length ?? 0}
            metrics={metrics.data?.length ?? 0}
            payloads={payloads.data?.length ?? 0}
            query={run}
          />
        </TabsContent>
        <TabsContent value="metrics">
          <MetricsTable query={metrics} />
        </TabsContent>
        <TabsContent value="payloads">
          <PayloadsTable query={payloads} />
        </TabsContent>
        <TabsContent value="files">
          <FilesTable projectId={projectId} query={files} />
        </TabsContent>
      </Tabs>
    </Page>
  );
}

/** Summary section for run identity and stored artifact counts. */
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
          <div className="my-4 grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-3">
            <SummaryTile label="Scalar metrics" value={metrics} />
            <SummaryTile label="Payloads" value={payloads} />
            <SummaryTile label="Files" value={files} />
            <SummaryTile label="Samples" value={run.samples.length} />
          </div>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-3">
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

/** Searchable scalar metric table for a run. */
function MetricsTable({ query }: { query: QueryState<AnalyticsMetric[]> }) {
  const [search, setSearch] = useState("");
  const filtered = useMemo(() => {
    const term = search.toLowerCase().trim();
    if (!query.data || !term) return query.data ?? [];
    return query.data.filter((metric) =>
      [
        metric.sample_id,
        metric.run_sample_id,
        metric.data_profile_id,
        metric.field_id,
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
          <TableWrap>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Sample</TableHead>
                  <TableHead>Profile</TableHead>
                  <TableHead>Field</TableHead>
                  <TableHead>Value</TableHead>
                  <TableHead>Source</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {metrics.map((metric, index) => (
                  <TableRow key={`${metric.field_id}-${metric.run_sample_id}-${index}`}>
                    <TableCell>{metric.sample_id ?? metric.run_sample_id ?? "—"}</TableCell>
                    <TableCell>{metric.data_profile_id}</TableCell>
                    <TableCell className="font-mono">{metric.field_id}</TableCell>
                    <TableCell>{formatMetricValue(metric)}</TableCell>
                    <TableCell className="max-w-[360px] overflow-hidden text-ellipsis whitespace-nowrap">
                      {metric.source_file_id ?? "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableWrap>
        </>
      )}
    </AsyncBlock>
  );
}

/** Table payload list with an inline preview for selected payloads. */
function PayloadsTable({ query }: { query: QueryState<AnalyticsPayload[]> }) {
  const [selected, setSelected] = useState<AnalyticsPayload | null>(null);
  return (
    <AsyncBlock query={query} empty="No table payloads were stored.">
      {(payloads) => (
        <>
          <TableWrap>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Payload</TableHead>
                  <TableHead>Sample</TableHead>
                  <TableHead>Profile</TableHead>
                  <TableHead>Rows</TableHead>
                  <TableHead>Columns</TableHead>
                  <TableHead className="text-right" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {payloads.map((payload) => (
                  <TableRow key={`${payload.payload_name}-${payload.run_sample_id ?? "run"}`}>
                    <TableCell className="font-bold">{payload.payload_name}</TableCell>
                    <TableCell>{payload.run_sample_id ?? "—"}</TableCell>
                    <TableCell>{payload.data_profile_id}</TableCell>
                    <TableCell>{payload.row_count}</TableCell>
                    <TableCell>{payload.columns.length}</TableCell>
                    <TableCell className="text-right">
                      <Button onClick={() => setSelected(payload)} size="sm" type="button">
                        View
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableWrap>
          {selected && <PayloadPreview payload={selected} />}
        </>
      )}
    </AsyncBlock>
  );
}

/** Snapshot preview of the first rows and columns in a table payload. */
function PayloadPreview({ payload }: { payload: AnalyticsPayload }) {
  const rows = payload.rows.slice(0, 25);
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{payload.payload_name}</CardTitle>
          <p className="mb-0 mt-1 text-[#657082]">
            {payload.row_count} rows from {payload.source_file_id ?? "stored payload"}
          </p>
        </div>
      </CardHeader>
      <CardContent>
        <TableWrap className="mt-0">
          <Table>
            <TableHeader>
              <TableRow>
                {payload.columns.slice(0, 40).map((column) => (
                  <TableHead key={column}>{column}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row, index) => (
                <TableRow key={index}>
                  {payload.columns.slice(0, 40).map((column) => (
                    <TableCell key={column}>{String(row[column] ?? "—")}</TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableWrap>
      </CardContent>
    </Card>
  );
}

/** Stored file table with links to generated report artifacts. */
function FilesTable({
  projectId,
  query,
}: {
  projectId: string;
  query: QueryState<Awaited<ReturnType<typeof listProjectRunFiles>>>;
}) {
  return (
    <AsyncBlock query={query} empty="No files were stored.">
      {(files: StoredFile[]) => (
        <TableWrap>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Kind</TableHead>
                <TableHead>Path</TableHead>
                <TableHead>Size</TableHead>
                <TableHead>SHA256</TableHead>
                <TableHead className="text-right" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {files.map((file) => (
                <TableRow key={file.file_id}>
                  <TableCell>{file.kind}</TableCell>
                  <TableCell className="max-w-[360px] overflow-hidden text-ellipsis whitespace-nowrap">
                      {shortPath(file.path ?? file.uri ?? file.file_id)}
                  </TableCell>
                  <TableCell>{formatBytes(file.size_bytes ?? 0)}</TableCell>
                  <TableCell className="font-mono">
                    {file.sha256?.slice(0, 12) ?? "—"}
                  </TableCell>
                  <TableCell className="text-right">
                    {file.kind.endsWith("report") && (
                      <Button asChild size="sm">
                        <a
                          href={fileContentUrl(file, projectId)}
                          rel="noreferrer"
                          target="_blank"
                        >
                          <ExternalLink size={14} /> Open
                        </a>
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableWrap>
      )}
    </AsyncBlock>
  );
}
