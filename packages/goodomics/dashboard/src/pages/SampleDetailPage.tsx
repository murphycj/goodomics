import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ExternalLink } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type {
  AnalyticsMetric,
  AnalyticsPayload,
  GoodomicsSample,
  SampleRun,
  StoredFile,
} from "../api";
import {
  fileContentUrl,
  getProjectSample,
  listProjectRunFiles,
  listProjectRunPayloads,
  listProjectSampleRunMetrics,
  listProjectSampleRuns,
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
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

export function SampleDetailPage({
  projectId,
  sampleId,
}: {
  projectId: string;
  sampleId: string;
}) {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const sample = useQuery({
    queryKey: ["project-sample", projectId, sampleId],
    queryFn: () => getProjectSample(projectId, sampleId),
  });
  const runs = useQuery({
    queryKey: ["project-sample-runs", projectId, sampleId],
    queryFn: () => listProjectSampleRuns(projectId, sampleId),
  });
  const selectedRun = useMemo(
    () => runs.data?.find((run) => run.run_id === selectedRunId) ?? null,
    [runs.data, selectedRunId],
  );
  const metrics = useQuery({
    queryKey: ["project-sample-run-metrics", projectId, sampleId, selectedRunId],
    queryFn: () =>
      selectedRunId
        ? listProjectSampleRunMetrics(projectId, sampleId, selectedRunId)
        : Promise.resolve([]),
    enabled: Boolean(selectedRunId),
  });
  const payloads = useQuery({
    queryKey: ["project-sample-run-payloads", projectId, sampleId, selectedRunId],
    queryFn: () =>
      selectedRunId
        ? listProjectRunPayloads(projectId, selectedRunId)
        : Promise.resolve([]),
    enabled: Boolean(selectedRunId),
  });
  const files = useQuery({
    queryKey: ["project-sample-run-files", projectId, sampleId, selectedRunId],
    queryFn: () =>
      selectedRunId ? listProjectRunFiles(projectId, selectedRunId) : Promise.resolve([]),
    enabled: Boolean(selectedRunId),
  });

  useEffect(() => {
    if (!runs.data?.length) {
      setSelectedRunId(null);
      return;
    }
    if (!selectedRunId || !runs.data.some((run) => run.run_id === selectedRunId)) {
      setSelectedRunId(runs.data[0].run_id);
    }
  }, [runs.data, selectedRunId]);

  return (
    <Page
      title={sample.data?.sample_name ?? sampleId}
      subtitle="Sample-level metrics, payloads, and stored files."
    >
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Button asChild variant="secondary">
          <Link to="/project/$projectId" params={{ projectId }}>
            Back to samples
          </Link>
        </Button>
        <RunSelector
          onSelect={setSelectedRunId}
          query={runs}
          selectedRunId={selectedRunId}
        />
        {selectedRunId && (
          <Button asChild variant="secondary">
            <Link
              to="/project/$projectId/runs/$runId"
              params={{ projectId, runId: selectedRunId }}
            >
              <ExternalLink size={16} /> Open run
            </Link>
          </Button>
        )}
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
          <SampleOverview
            files={files.data?.length ?? 0}
            metrics={metrics.data?.length ?? 0}
            payloads={payloads.data?.length ?? 0}
            query={sample}
            runCount={runs.data?.length ?? 0}
            selectedRun={selectedRun}
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

function RunSelector({
  onSelect,
  query,
  selectedRunId,
}: {
  onSelect: (runId: string) => void;
  query: QueryState<SampleRun[]>;
  selectedRunId: string | null;
}) {
  if (query.isLoading) {
    return <span className="text-sm text-[#657082]">Loading runs...</span>;
  }
  if (query.error) {
    return <span className="text-sm text-[#b42318]">{query.error.message}</span>;
  }
  if (!query.data?.length) {
    return <span className="text-sm text-[#657082]">No associated runs</span>;
  }
  return (
    <Select value={selectedRunId ?? undefined} onValueChange={onSelect}>
      <SelectTrigger className="w-[min(100%,24rem)]" aria-label="Select run">
        <SelectValue placeholder="Select run" />
      </SelectTrigger>
      <SelectContent>
        {query.data.map((run) => (
          <SelectItem key={run.run_id} value={run.run_id}>
            {run.name ?? run.run_id}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function SampleOverview({
  files,
  metrics,
  payloads,
  query,
  runCount,
  selectedRun,
}: {
  files: number;
  metrics: number;
  payloads: number;
  query: QueryState<GoodomicsSample>;
  runCount: number;
  selectedRun: SampleRun | null;
}) {
  return (
    <AsyncBlock query={query} empty="Sample not found.">
      {(sample) => (
        <>
          <div className="my-4 grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-3">
            <SummaryTile label="Scalar metrics" value={metrics} />
            <SummaryTile label="Payloads" value={payloads} />
            <SummaryTile label="Files" value={files} />
            <SummaryTile label="Runs" value={runCount} />
          </div>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-3">
            <Detail label="Sample ID" value={sample.sample_id} />
            <Detail label="Sample name" value={sample.sample_name ?? "—"} />
            <Detail label="Subject" value={sample.subject_id ?? "—"} />
            <Detail label="Current run" value={selectedRun?.name ?? selectedRun?.run_id ?? "—"} />
            <Detail
              label="Run created"
              value={selectedRun ? formatDate(selectedRun.created_at) : "—"}
            />
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
          <TableWrap>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Sample</TableHead>
                  <TableHead>Profile</TableHead>
                  <TableHead>Metric</TableHead>
                  <TableHead>Value</TableHead>
                  <TableHead>Source</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {metrics.map((metric, index) => (
                  <TableRow key={`${metric.metric_key}-${metric.run_sample_key}-${index}`}>
                    <TableCell>{metric.sample_key ?? metric.run_sample_key ?? "—"}</TableCell>
                    <TableCell>{metric.data_profile_key}</TableCell>
                    <TableCell className="font-mono">{metric.metric_key}</TableCell>
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
                  <TableRow key={`${payload.payload_name}-${payload.run_sample_key ?? "run"}`}>
                    <TableCell className="font-bold">{payload.payload_name}</TableCell>
                    <TableCell>{payload.run_sample_key ?? "—"}</TableCell>
                    <TableCell>{payload.data_profile_key}</TableCell>
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

function FilesTable({
  projectId,
  query,
}: {
  projectId: string;
  query: QueryState<StoredFile[]>;
}) {
  return (
    <AsyncBlock query={query} empty="No files were stored.">
      {(files) => (
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
