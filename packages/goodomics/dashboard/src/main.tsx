import { QueryClientProvider } from "@tanstack/react-query";
import { useQuery } from "@tanstack/react-query";
import {
  RouterProvider,
  createRootRoute,
  createRoute,
  createRouter,
} from "@tanstack/react-router";
import { createRoot } from "react-dom/client";
import { Layout } from "./components/layout/Layout";
import { getProject } from "./api";
import { queryClient } from "./lib/queryClient";
import { DatabasePage } from "./pages/DatabasePage";
import { HomePage } from "./pages/HomePage";
import { InsightsPage } from "./pages/InsightsPage";
import { PoliciesPage } from "./pages/PoliciesPage";
import { ProjectDataBrowserPage } from "./pages/ProjectDataBrowserPage";
import { ProjectHomePage } from "./pages/ProjectHomePage";
import { ReportsPage } from "./pages/ReportsPage";
import { RunDetailPage } from "./pages/RunDetailPage";
import { SampleDetailPage } from "./pages/SampleDetailPage";
import { SettingsPage } from "./pages/SettingsPage";
import "./styles.css";

const rootRoute = createRootRoute({ component: Layout });
const homeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: HomePage,
});
const projectRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/project/$projectId",
  component: ProjectRouteAdapter,
});
const runDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/project/$projectId/runs/$runId",
  component: RunDetailRouteAdapter,
});
const runsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/project/$projectId/runs",
  component: RunsRouteAdapter,
});
const samplesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/project/$projectId/samples",
  component: SamplesRouteAdapter,
});
const sampleGroupsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/project/$projectId/sample-groups",
  component: SampleGroupsRouteAdapter,
});
const sampleDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/project/$projectId/samples/$sampleId",
  component: SampleDetailRouteAdapter,
});
const reportsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/project/$projectId/reports",
  component: ReportsRouteAdapter,
});
const insightsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/project/$projectId/insights",
  component: InsightsRouteAdapter,
});
const policiesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/project/$projectId/qc-policies",
  component: PoliciesPage,
});
const databaseRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/project/$projectId/database",
  component: DatabaseRouteAdapter,
});
const settingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/project/$projectId/settings",
  component: SettingsRouteAdapter,
});

const router = createRouter({
  routeTree: rootRoute.addChildren([
    homeRoute,
    projectRoute,
    runDetailRoute,
    runsRoute,
    samplesRoute,
    sampleGroupsRoute,
    sampleDetailRoute,
    reportsRoute,
    insightsRoute,
    policiesRoute,
    databaseRoute,
    settingsRoute,
  ]),
});

/** Project landing adapter that redirects to the configured default report when present. */
function ProjectRouteAdapter() {
  const { projectId } = projectRoute.useParams();
  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => getProject(projectId),
  });
  if (project.data?.default_report_id) {
    return (
      <ReportsPage
        initialReportId={project.data.default_report_id}
        projectId={projectId}
      />
    );
  }
  return <ProjectHomePage projectId={projectId} />;
}

/** Route adapter that injects the current project id into the runs page. */
function RunsRouteAdapter() {
  const { projectId } = runsRoute.useParams();
  return <ProjectDataBrowserPage activeTab="runs" projectId={projectId} />;
}

/** Route adapter that injects the current project id into the samples page. */
function SamplesRouteAdapter() {
  const { projectId } = samplesRoute.useParams();
  return <ProjectDataBrowserPage activeTab="samples" projectId={projectId} />;
}

/** Route adapter that injects the current project id into the sample groups page. */
function SampleGroupsRouteAdapter() {
  const { projectId } = sampleGroupsRoute.useParams();
  return (
    <ProjectDataBrowserPage activeTab="sample-groups" projectId={projectId} />
  );
}

/** Route adapter that injects the current project id into the reports page. */
function ReportsRouteAdapter() {
  const { projectId } = reportsRoute.useParams();
  return <ReportsPage projectId={projectId} />;
}

/** Route adapter that injects the current project id into the insights page. */
function InsightsRouteAdapter() {
  const { projectId } = insightsRoute.useParams();
  return <InsightsPage projectId={projectId} />;
}

/** Route adapter for run detail params. */
function RunDetailRouteAdapter() {
  const { projectId, runId } = runDetailRoute.useParams();
  return <RunDetailPage projectId={projectId} runId={runId} />;
}

/** Route adapter for sample detail params. */
function SampleDetailRouteAdapter() {
  const { projectId, sampleId } = sampleDetailRoute.useParams();
  return <SampleDetailPage projectId={projectId} sampleId={sampleId} />;
}

/** Route adapter that injects the current project id into the database browser. */
function DatabaseRouteAdapter() {
  const { projectId } = databaseRoute.useParams();
  return <DatabasePage projectId={projectId} />;
}

/** Route adapter that injects the current project id into settings. */
function SettingsRouteAdapter() {
  const { projectId } = settingsRoute.useParams();
  return <SettingsPage projectId={projectId} />;
}

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

createRoot(document.getElementById("root")!).render(
  <QueryClientProvider client={queryClient}>
    <RouterProvider router={router} />
  </QueryClientProvider>,
);
