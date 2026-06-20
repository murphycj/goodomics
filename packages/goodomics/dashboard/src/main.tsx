import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { createRoot } from 'react-dom/client';
import {
  Link,
  Outlet,
  RouterProvider,
  createRootRoute,
  createRoute,
  createRouter,
} from '@tanstack/react-router';
import {
  Database,
  FileCode2,
  FileText,
  FlaskConical,
  Gauge,
  Layers3,
  Settings,
} from 'lucide-react';
import { listNamedRows, listRuns, listTemplates } from './api';
import './styles.css';

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

function Layout() {
  return (
    <main className="shell">
      <aside>
        <h1>Goodomics</h1>
        <p>Runs, reports, templates, and QC policies.</p>
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
  const runs = useQuery({ queryKey: ['runs'], queryFn: listRuns });
  return (
    <Page title="Runs" subtitle="Browse stored Goodomics runs and open run details.">
      <DataState query={runs} empty="No runs have been stored yet." />
    </Page>
  );
}

function ReportsPage() {
  const reports = useQuery({
    queryKey: ['reports'],
    queryFn: () => listNamedRows('/api/v1/database/tables/reports/rows'),
  });
  return (
    <Page title="Reports" subtitle="Render and export standalone HTML reports.">
      <DataState query={reports} empty="No rendered reports yet." />
    </Page>
  );
}

function TemplatesPage() {
  const templates = useQuery({ queryKey: ['templates'], queryFn: listTemplates });
  return (
    <Page title="Report template editor" subtitle="Edit DB-backed templates and export YAML or JSON for CLI use.">
      <DataState query={templates} empty="Create a template to begin editing." />
    </Page>
  );
}

function CohortsPage() {
  const cohorts = useQuery({ queryKey: ['cohorts'], queryFn: () => listNamedRows('/api/v1/cohorts') });
  return (
    <Page title="Cohorts" subtitle="Group runs and samples for cohort-aware QC.">
      <DataState query={cohorts} empty="No cohorts configured." />
    </Page>
  );
}

function PoliciesPage() {
  const policies = useQuery({ queryKey: ['qc-policies'], queryFn: () => listNamedRows('/api/v1/qc-policies') });
  return (
    <Page title="QC policies / thresholds" subtitle="Manage validated threshold sets for quality decisions.">
      <DataState query={policies} empty="No QC policies configured." />
    </Page>
  );
}

function DatabasePage() {
  const tables = useQuery({ queryKey: ['tables'], queryFn: () => listNamedRows('/api/v1/database/tables') });
  return (
    <Page title="Database editor" subtitle="Typed, validated table edits without arbitrary SQL access.">
      <DataState query={tables} empty="No editable tables available." />
    </Page>
  );
}

function SettingsPage() {
  return (
    <Page title="Settings" subtitle="Dashboard and API configuration.">
      <div className="card">API namespace: <code>/api/v1</code></div>
    </Page>
  );
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

function DataState({ query, empty }: { query: { isLoading: boolean; error: Error | null; data?: unknown[] }; empty: string }) {
  if (query.isLoading) return <div className="card">Loading…</div>;
  if (query.error) return <div className="card error">{query.error.message}</div>;
  if (!query.data?.length) return <div className="card muted">{empty}</div>;
  return <pre className="card">{JSON.stringify(query.data, null, 2)}</pre>;
}

const rootRoute = createRootRoute({ component: Layout });
const runsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/', component: RunsPage });
const reportsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/reports', component: ReportsPage });
const templatesRoute = createRoute({ getParentRoute: () => rootRoute, path: '/templates', component: TemplatesPage });
const cohortsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/cohorts', component: CohortsPage });
const policiesRoute = createRoute({ getParentRoute: () => rootRoute, path: '/qc-policies', component: PoliciesPage });
const databaseRoute = createRoute({ getParentRoute: () => rootRoute, path: '/database', component: DatabasePage });
const settingsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/settings', component: SettingsPage });

const router = createRouter({
  routeTree: rootRoute.addChildren([
    runsRoute,
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
