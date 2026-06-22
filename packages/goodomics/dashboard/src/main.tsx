import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import {
  Link,
  Outlet,
  RouterProvider,
  createRootRoute,
  createRoute,
  createRouter,
  useNavigate,
} from '@tanstack/react-router';
import {
  ChevronFirst,
  ChevronLast,
  ChevronLeft,
  ChevronRight,
  Database,
  ExternalLink,
  FileCode2,
  FileText,
  FlaskConical,
  Gauge,
  Layers3,
  Search,
  Settings,
} from 'lucide-react';
import { useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  AnalyticsMetric,
  AnalyticsPayload,
  GoodomicsRun,
  fileContentUrl,
  getDatabaseSummary,
  getRun,
  listNamedRows,
  listRunFiles,
  listRunMetrics,
  listRunPayloads,
  listRuns,
  listTemplates,
} from './api';
import './styles.css';

const RUNS_PAGE_SIZE = 50;
const queryClient = new QueryClient();
const navItems = [
  { to: '/', label: 'Runs', icon: FlaskConical },
  { to: '/reports', label: 'Reports', icon: FileText },
  { to: '/templates', label: 'Template editor', icon: FileCode2 },
  { to: '/cohorts', label: 'Cohorts', icon: Layers3 },
  { to: '/qc-policies', label: 'QC policies', icon: Gauge },
  { to: '/database', label: 'Database editor', icon: Database },
  { to: '/settings', label: 'Settings', icon: Settings },
] as const;

type QueryState<T> = { isLoading: boolean; error: Error | null; data?: T };

function Layout() {
  return (
    <main className="shell">
      <aside>
        <h1>Goodomics</h1>
        <p>QC context for computational omics runs.</p>
        <nav>
          {navItems.map(({ to, label, icon: Icon }) => (
            <Link key={to} to={to} activeProps={{ className: 'active' }}>
              <Icon size={18} /> {label}
            </Link>
          ))}
        </nav>
      </aside>
      <section className="content">
        <Outlet />
      </section>
    </main>
  );
}

function RunsPage() {
  const [page, setPage] = useState(0);
  const offset = page * RUNS_PAGE_SIZE;
  const runs = useQuery({
    queryKey: ['runs', offset, RUNS_PAGE_SIZE],
    queryFn: () => listRuns({ limit: RUNS_PAGE_SIZE, offset }),
  });
  return (
    <Page title="Runs" subtitle="Browse stored runs and inspect their QC context.">
      <AsyncBlock query={runs} empty="No runs have been stored yet.">
        {(data) => (
          <>
            {data.items.length === 0 ? (
              <div className="panel muted">No runs have been stored yet.</div>
            ) : (
              <RunsTable runs={data.items} />
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
    </Page>
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
        {start.toLocaleString()}-{end.toLocaleString()} of {total.toLocaleString()} runs
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

function RunsTable({ runs }: { runs: GoodomicsRun[] }) {
  const navigate = useNavigate();
  const openRun = (runId: string) => {
    void navigate({ to: '/runs/$runId', params: { runId } });
  };

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Run</th>
            <th>Project</th>
            <th>Assay</th>
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
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  openRun(run.run_id);
                }
              }}
              role="link"
              tabIndex={0}
            >
              <td className="strong">{run.run_id}</td>
              <td>{run.project ?? '—'}</td>
              <td>{run.assay ?? '—'}</td>
              <td>{formatDate(run.created_at)}</td>
              <td>{run.samples.length}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RunDetailPage() {
  const { runId } = runDetailRoute.useParams();
  const [tab, setTab] = useState<'overview' | 'metrics' | 'payloads' | 'files'>('overview');
  const run = useQuery({ queryKey: ['run', runId], queryFn: () => getRun(runId) });
  const metrics = useQuery({ queryKey: ['run-metrics', runId], queryFn: () => listRunMetrics(runId) });
  const payloads = useQuery({ queryKey: ['run-payloads', runId], queryFn: () => listRunPayloads(runId) });
  const files = useQuery({ queryKey: ['run-files', runId], queryFn: () => listRunFiles(runId) });

  return (
    <Page title={runId} subtitle="Run-level metrics, payloads, and stored files.">
      <div className="topbar">
        <Link className="button secondary" to="/">
          Back to runs
        </Link>
        {files.data
          ?.filter((file) => file.kind === 'multiqc_report')
          .slice(0, 1)
          .map((file) => (
            <a
              className="button"
              href={fileContentUrl(file)}
              key={file.id}
              rel="noreferrer"
              target="_blank"
            >
              <ExternalLink size={16} /> MultiQC report
            </a>
          ))}
      </div>
      <div className="tabs">
        {(['overview', 'metrics', 'payloads', 'files'] as const).map((item) => (
          <button
            className={tab === item ? 'active' : ''}
            key={item}
            onClick={() => setTab(item)}
            type="button"
          >
            {titleCase(item)}
          </button>
        ))}
      </div>
      {tab === 'overview' && (
        <RunOverview
          files={files.data?.length ?? 0}
          metrics={metrics.data?.length ?? 0}
          payloads={payloads.data?.length ?? 0}
          query={run}
        />
      )}
      {tab === 'metrics' && <MetricsTable query={metrics} />}
      {tab === 'payloads' && <PayloadsTable query={payloads} />}
      {tab === 'files' && <FilesTable query={files} />}
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
            <Detail label="Project" value={run.project ?? '—'} />
            <Detail label="Assay" value={run.assay ?? '—'} />
            <Detail label="Created" value={formatDate(run.created_at)} />
          </div>
        </>
      )}
    </AsyncBlock>
  );
}

function MetricsTable({ query }: { query: QueryState<AnalyticsMetric[]> }) {
  const [search, setSearch] = useState('');
  const filtered = useMemo(() => {
    const term = search.toLowerCase().trim();
    if (!query.data || !term) return query.data ?? [];
    return query.data.filter((metric) =>
      [
        metric.sample_id,
        metric.tool,
        metric.module,
        metric.stage,
        metric.metric_key,
        metric.value_text,
        metric.source_file,
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(term)),
    );
  }, [query.data, search]);

  return (
    <AsyncBlock query={{ ...query, data: filtered }} empty="No scalar metrics were stored.">
      {(metrics) => (
        <>
          <SearchBox value={search} onChange={setSearch} placeholder="Filter metrics" />
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Sample</th>
                  <th>Tool</th>
                  <th>Metric</th>
                  <th>Value</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {metrics.map((metric, index) => (
                  <tr key={`${metric.metric_key}-${metric.sample_id}-${index}`}>
                    <td>{metric.sample_id ?? '—'}</td>
                    <td>{metric.tool ?? '—'}</td>
                    <td className="mono">{metric.metric_key}</td>
                    <td>{formatValue(metric)}</td>
                    <td className="truncate">{shortPath(metric.source_file)}</td>
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
                  <th>Tool</th>
                  <th>Rows</th>
                  <th>Columns</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {payloads.map((payload) => (
                  <tr key={`${payload.payload_name}-${payload.sample_id ?? 'run'}`}>
                    <td className="strong">{payload.payload_name}</td>
                    <td>{payload.sample_id ?? '—'}</td>
                    <td>{payload.tool ?? '—'}</td>
                    <td>{payload.row_count}</td>
                    <td>{payload.columns.length}</td>
                    <td className="right">
                      <button className="button compact" onClick={() => setSelected(payload)} type="button">
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
          <p>{payload.row_count} rows from {shortPath(payload.source_file)}</p>
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
                  <td key={column}>{String(row[column] ?? '—')}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function FilesTable({ query }: { query: QueryState<Awaited<ReturnType<typeof listRunFiles>>> }) {
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
                  <td className="mono">{file.sha256?.slice(0, 12) ?? '—'}</td>
                  <td className="right">
                    {file.kind.endsWith('report') && (
                      <a className="button compact" href={fileContentUrl(file)} rel="noreferrer" target="_blank">
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

function ReportsPage() {
  const reports = useQuery({
    queryKey: ['reports'],
    queryFn: () => listNamedRows('/api/v1/database/tables/reports/rows'),
  });
  return (
    <Page title="Reports" subtitle="Rendered standalone reports.">
      <GenericRows query={reports} empty="No rendered reports yet." />
    </Page>
  );
}

function TemplatesPage() {
  const templates = useQuery({ queryKey: ['templates'], queryFn: listTemplates });
  return (
    <Page title="Report template editor" subtitle="Edit DB-backed templates and export YAML or JSON.">
      <GenericRows query={templates} empty="Create a template to begin editing." />
    </Page>
  );
}

function CohortsPage() {
  const cohorts = useQuery({ queryKey: ['cohorts'], queryFn: () => listNamedRows('/api/v1/cohorts') });
  return (
    <Page title="Cohorts" subtitle="Group runs and samples for cohort-aware QC.">
      <GenericRows query={cohorts} empty="No cohorts configured." />
    </Page>
  );
}

function PoliciesPage() {
  const policies = useQuery({ queryKey: ['qc-policies'], queryFn: () => listNamedRows('/api/v1/qc-policies') });
  return (
    <Page title="QC policies" subtitle="Manage threshold sets for quality decisions.">
      <GenericRows query={policies} empty="No QC policies configured." />
    </Page>
  );
}

function DatabasePage() {
  const summary = useQuery({ queryKey: ['database-summary'], queryFn: getDatabaseSummary });
  const tables = useQuery({ queryKey: ['tables'], queryFn: () => listNamedRows('/api/v1/database/tables') });
  return (
    <Page title="Database editor" subtitle="Control database and analytics store status.">
      <AsyncBlock query={summary} empty="No database summary available.">
        {(data) => (
          <>
            <div className="summary-grid">
              <SummaryTile label="SQLite" value={formatBytes(data.sqlite_size_bytes)} />
              <SummaryTile label="DuckDB" value={formatBytes(data.duckdb_size_bytes)} />
              <SummaryTile label="Files" value={formatBytes(data.file_size_bytes)} />
              <SummaryTile label="Runs" value={data.total_runs} />
              <SummaryTile label="Samples" value={data.total_samples} />
              <SummaryTile label="Scalar metrics" value={data.total_scalar_metrics} />
              <SummaryTile label="Payloads" value={data.total_payloads} />
            </div>
            <div className="two-column">
              <CountsTable title="Control tables" rows={data.control_tables} />
              <CountsTable title="Analytics tables" rows={data.analytics_tables} />
            </div>
          </>
        )}
      </AsyncBlock>
      <section className="panel">
        <h3>Editable Tables</h3>
        <GenericRows query={tables} empty="No editable tables available." />
      </section>
    </Page>
  );
}

function SettingsPage() {
  return (
    <Page title="Settings" subtitle="Dashboard and API configuration.">
      <div className="panel">API namespace: <code>/api/v1</code></div>
    </Page>
  );
}

function CountsTable({ title, rows }: { title: string; rows: { name: string; rows: number }[] }) {
  return (
    <section className="panel">
      <h3>{title}</h3>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Table</th>
              <th className="right">Rows</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.name}>
                <td>{row.name}</td>
                <td className="right">{row.rows.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function GenericRows<T extends unknown[]>({ query, empty }: { query: QueryState<T>; empty: string }) {
  return (
    <AsyncBlock query={query} empty={empty}>
      {(rows) => <pre className="json-block">{JSON.stringify(rows, null, 2)}</pre>}
    </AsyncBlock>
  );
}

function AsyncBlock<T>({
  children,
  empty,
  query,
}: {
  children: (data: T) => React.ReactNode;
  empty: string;
  query: QueryState<T>;
}) {
  if (query.isLoading) return <div className="panel muted">Loading...</div>;
  if (query.error) return <div className="panel error">{query.error.message}</div>;
  if (Array.isArray(query.data) && query.data.length === 0) {
    return <div className="panel muted">{empty}</div>;
  }
  if (!query.data) return <div className="panel muted">{empty}</div>;
  return <>{children(query.data)}</>;
}

function Page({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <>
      <header>
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </header>
      {children}
    </>
  );
}

function SearchBox({
  onChange,
  placeholder,
  value,
}: {
  onChange: (value: string) => void;
  placeholder: string;
  value: string;
}) {
  return (
    <label className="search">
      <Search size={16} />
      <input onChange={(event) => onChange(event.target.value)} placeholder={placeholder} value={value} />
    </label>
  );
}

function SummaryTile({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="summary-tile">
      <span>{label}</span>
      <strong>{typeof value === 'number' ? value.toLocaleString() : value}</strong>
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="detail">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function formatDate(value: string) {
  return new Date(value).toLocaleString();
}

function formatBytes(value: number) {
  if (!value) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  return `${(value / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function formatValue(metric: AnalyticsMetric) {
  const value = metric.value_num ?? metric.value_text ?? '—';
  return `${typeof value === 'number' ? value.toLocaleString() : value}${metric.unit ? ` ${metric.unit}` : ''}`;
}

function shortPath(path: string) {
  const parts = path.split('/');
  return parts.length > 4 ? `.../${parts.slice(-4).join('/')}` : path;
}

function titleCase(value: string) {
  return value.slice(0, 1).toUpperCase() + value.slice(1);
}

const rootRoute = createRootRoute({ component: Layout });
const runsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/', component: RunsPage });
const runDetailRoute = createRoute({ getParentRoute: () => rootRoute, path: '/runs/$runId', component: RunDetailPage });
const reportsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/reports', component: ReportsPage });
const templatesRoute = createRoute({ getParentRoute: () => rootRoute, path: '/templates', component: TemplatesPage });
const cohortsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/cohorts', component: CohortsPage });
const policiesRoute = createRoute({ getParentRoute: () => rootRoute, path: '/qc-policies', component: PoliciesPage });
const databaseRoute = createRoute({ getParentRoute: () => rootRoute, path: '/database', component: DatabasePage });
const settingsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/settings', component: SettingsPage });

const router = createRouter({
  routeTree: rootRoute.addChildren([
    runsRoute,
    runDetailRoute,
    reportsRoute,
    templatesRoute,
    cohortsRoute,
    policiesRoute,
    databaseRoute,
    settingsRoute,
  ]),
});

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}

createRoot(document.getElementById('root')!).render(
  <QueryClientProvider client={queryClient}>
    <RouterProvider router={router} />
  </QueryClientProvider>,
);
