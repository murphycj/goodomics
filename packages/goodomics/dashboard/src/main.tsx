import { QueryClientProvider } from "@tanstack/react-query";
import {
  RouterProvider,
  createRootRoute,
  createRoute,
  createRouter,
} from "@tanstack/react-router";
import { createRoot } from "react-dom/client";
import { Layout } from "./components/layout/Layout";
import { queryClient } from "./lib/queryClient";
import { CohortsPage } from "./pages/CohortsPage";
import { DatabasePage } from "./pages/DatabasePage";
import { HomePage } from "./pages/HomePage";
import { PoliciesPage } from "./pages/PoliciesPage";
import { ProjectSamplesPage } from "./pages/ProjectSamplesPage";
import { ReportsPage } from "./pages/ReportsPage";
import { RunDetailPage } from "./pages/RunDetailPage";
import { SampleDetailPage } from "./pages/SampleDetailPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TemplatesPage } from "./pages/TemplatesPage";
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
const sampleDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/project/$projectId/samples/$sampleId",
  component: SampleDetailRouteAdapter,
});
const reportsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/project/$projectId/reports",
  component: ReportsPage,
});
const templatesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/project/$projectId/templates",
  component: TemplatesPage,
});
const cohortsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/project/$projectId/cohorts",
  component: CohortsPage,
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
    sampleDetailRoute,
    reportsRoute,
    templatesRoute,
    cohortsRoute,
    policiesRoute,
    databaseRoute,
    settingsRoute,
  ]),
});

function ProjectRouteAdapter() {
  const { projectId } = projectRoute.useParams();
  return <ProjectSamplesPage projectId={projectId} />;
}

function RunDetailRouteAdapter() {
  const { projectId, runId } = runDetailRoute.useParams();
  return <RunDetailPage projectId={projectId} runId={runId} />;
}

function SampleDetailRouteAdapter() {
  const { projectId, sampleId } = sampleDetailRoute.useParams();
  return <SampleDetailPage projectId={projectId} sampleId={sampleId} />;
}

function DatabaseRouteAdapter() {
  const { projectId } = databaseRoute.useParams();
  return <DatabasePage projectId={projectId} />;
}

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
